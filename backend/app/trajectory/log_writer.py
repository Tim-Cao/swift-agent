"""SessionLogWriter:追加式 JSONL 事件写入器。

设计要点(参考 deepseek-harness ``SessionWriteBehind`` / ``JsonlSessionPersistence``):

- **同步 fsync**:每条事件写完 ``flush()`` 一下,保证 SSE 流结束时磁盘也有
  完整记录;数据量很小(单轮 ~10-100 行),同步开销可忽略
- **per-session Lock**:同一 session 并发写(理论上不应该发生,但前端
  双击发送可能触发)用 ``asyncio.Lock`` 串行化
- **Header 一次性**:首次 append 时写 header;之后 append 只追事件
- **Append-only**:永远 ``"a"`` 模式 open,不重写历史

文件布局::

    data/sessions/<session_id>/session.jsonl

    {"type":"session","version":1,"id":"...","created_at":...}\n
    {"seq":1,"time":...,"type":"turn_start","data":{"turn":0}}\n
    {"seq":2,"time":...,"type":"user_message","data":{"content":"..."}}\n
    ...
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from app.trajectory.schema import (
    SESSION_LOG_FORMAT_VERSION,
    SessionEvent,
    SessionEventType,
    SessionHeader,
)

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """JSON 兜底序列化:处理 LangChain Message / 任意对象。"""
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:  # noqa: BLE001
            return str(obj)
    if hasattr(obj, "__dict__"):
        try:
            return dict(obj.__dict__)
        except Exception:  # noqa: BLE001
            return str(obj)
    return str(obj)


class SessionLogWriter:
    """单个会话的 JSONL 写入器。

    用法::

        writer = SessionLogWriter(session_id, root=Path("./data/sessions"))
        await writer.open(agent_name="supervisor", model="gpt-4o-mini")
        await writer.append("user_message", {"content": "hi"})
        await writer.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "Hel"})
        ...
        await writer.append("turn_end", {"turn": 0, "reason": "normal"})
        await writer.close()
    """

    def __init__(
        self,
        session_id: str,
        root: Path | str = "./data/sessions",
        fsync: bool = True,
    ) -> None:
        self.session_id = session_id
        self.root = Path(root)
        self.fsync = fsync
        self._dir = self.root / session_id
        self._path = self._dir / "session.jsonl"
        self._file = None  # type: ignore[assignment]
        self._seq = 0  # 已写入的事件 seq(不含 header)
        self._header_written = False
        self._was_empty_on_open = False  # open() 时文件是否为空(用于判断是否首次)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def open(
        self,
        agent_name: str | None = None,
        model: str | None = None,
    ) -> None:
        """打开会话日志:创建目录、写入 header(若不存在)、同步已存在的 seq。

        设置 ``_was_empty_on_open`` 标记:open 时文件为空(首次创建)=True,
        chat_service 据此判断"是否需要写 system_prompt(initial)"。
        """
        async with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            if self._file is None:
                # ``a`` 模式:已存在文件则追加,首次创建则空白
                self._file = await asyncio.to_thread(
                    lambda: open(self._path, "a", encoding="utf-8")
                )
            if not self._header_written and self._file.tell() == 0:
                self._was_empty_on_open = True
                header = SessionHeader(
                    version=SESSION_LOG_FORMAT_VERSION,
                    id=self.session_id,
                    created_at=time.time(),
                    agent_name=agent_name,
                    model=model,
                )
                line = json.dumps(
                    header.model_dump(),
                    ensure_ascii=False,
                    default=_json_default,
                )
                await asyncio.to_thread(self._file.write, line + "\n")
                if self.fsync:
                    await asyncio.to_thread(self._file.flush)
                    await asyncio.to_thread(os.fsync, self._file.fileno())
                self._header_written = True
                logger.info(
                    "SessionLogWriter opened (new): session=%s path=%s",
                    self.session_id, self._path,
                )
            else:
                self._was_empty_on_open = False
                # 文件已有内容:同步现有 seq,以便后续 append 接续计数
                self._header_written = True
                await self._sync_seq_from_disk()
                logger.info(
                    "SessionLogWriter opened (existing): session=%s path=%s",
                    self.session_id, self._path,
                )

    @property
    def was_empty_on_open(self) -> bool:
        """open() 时文件是否为空(首次创建会话=True)。"""
        return self._was_empty_on_open

    async def close(self) -> None:
        """关闭文件句柄。"""
        async with self._lock:
            if self._file is not None:
                await asyncio.to_thread(self._file.close)
                self._file = None

    async def _sync_seq_from_disk(self) -> None:
        """从磁盘现有 JSONL 里算出当前 max seq,让后续 append 接续计数。"""
        def _scan() -> int:
            max_seq = 0
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if obj.get("type") == "session":
                            continue
                        seq = obj.get("seq")
                        if isinstance(seq, int):
                            if seq > max_seq:
                                max_seq = seq
            except OSError:
                return 0
            return max_seq

        self._seq = await asyncio.to_thread(_scan)

    async def next_turn_index(self) -> int:
        """从已有 JSONL 算下一个 turn 号(=已有 turn_start.turn 的 max + 1,无则 0)。

        用于多轮对话:每次 ``stream_chat`` 启动前调一次,把 ``turn_index`` 接到上次之后。
        """
        def _scan() -> int:
            max_turn = -1
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if obj.get("type") != "turn_start":
                            continue
                        data = obj.get("data") or {}
                        t = data.get("turn")
                        if isinstance(t, int) and t > max_turn:
                            max_turn = t
            except OSError:
                return 0
            return max_turn + 1

        return await asyncio.to_thread(_scan)

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #

    async def append(
        self,
        event_type: SessionEventType,
        data: dict[str, Any] | None = None,
        time_override: float | None = None,
    ) -> SessionEvent:
        """追加一条事件。返回写出去的 ``SessionEvent``(含 seq / time)。"""
        if self._file is None:
            await self.open()
        async with self._lock:
            self._seq += 1
            event = SessionEvent(
                seq=self._seq,
                time=time_override if time_override is not None else time.time(),
                type=event_type,
                data=data or {},
            )
            line = json.dumps(
                event.model_dump(),
                ensure_ascii=False,
                default=_json_default,
            )
            await asyncio.to_thread(self._file.write, line + "\n")
            if self.fsync:
                await asyncio.to_thread(self._file.flush)
                await asyncio.to_thread(os.fsync, self._file.fileno())
            return event

    # ------------------------------------------------------------------ #
    # 上下文管理器支持
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "SessionLogWriter":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()