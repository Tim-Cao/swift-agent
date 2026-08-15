"""SessionLogReader:读 JSONL + 折叠成 Trajectory。

折叠算法(把事件流折叠成前端友好的结构):

1. 读 header → ``SessionHeader``
2. ``system_prompt`` 事件 → 折叠成 ``Trajectory.system_prompts`` 列表
   (session-level,不进 turn;参考 deepseek-harness 的 ``request/header`` 设计)
3. 按 ``turn_start`` 切 turn;``turn_end`` 标记结束
4. 每个 turn 内按 ``(turn, step)`` 分组:
   - ``assistant_chunk`` → 累积到当前 ``(turn, step)`` 的 assistant content
   - ``assistant_message`` → 替换 / 收尾(可能有 usage)
   - ``tool_call`` + ``tool_result`` → 配对成 ToolCallStep
   - ``file_emitted`` → 独立 step
5. ``turn_end`` 时统一排序 + 重新编号(已有 steps 与新生成的一并参与)
6. 汇总 ``TrajectorySummary``(turns / steps / 工具调用统计 / token 合计)

参考 deepseek-harness 的 ``TrajectorySnapshotBuilder``:
那边的事件更细分(``step/start`` / ``step/end`` 等),
我们这里用 turn 自然分组,跳过 ``step/start/end`` 这层包装。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from app.trajectory.schema import (
    AssistantStep,
    SessionEvent,
    SessionEventType,
    SessionHeader,
    SystemPromptRecord,
    ToolCallStep,
    Trajectory,
    TrajectoryStep,
    TrajectorySummary,
    TrajectoryToolCallSummary,
    TrajectoryTurn,
)

logger = logging.getLogger(__name__)


def _json_loads_safe(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None


class SessionLogReader:
    """读取并折叠 session JSONL。

    用法::

        reader = SessionLogReader(session_id, root=Path("./data/sessions"))
        trajectory = await reader.read()
        # 或只拿原始事件:
        events = await reader.read_events()
    """

    def __init__(self, session_id: str, root: Path | str = "./data/sessions") -> None:
        self.session_id = session_id
        self.root = Path(root)
        self._path = self.root / session_id / "session.jsonl"

    @property
    def exists(self) -> bool:
        return self._path.exists() and self._path.stat().st_size > 0

    # ------------------------------------------------------------------ #
    # 读原始事件
    # ------------------------------------------------------------------ #

    async def read_header(self) -> SessionHeader | None:
        """读第一行 header;文件不存在 / 空 → 返回 None。"""
        if not self._path.exists():
            return None
        # ``with open`` 在线程外异步不安全,直接读 + 关
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                first = f.readline().strip()
        except OSError as e:
            logger.warning("read_header failed session=%s: %s", self.session_id, e)
            return None
        if not first:
            return None
        obj = _json_loads_safe(first)
        if obj is None or obj.get("type") != "session":
            return None
        return SessionHeader.model_validate(obj)

    async def read_events(self) -> list[SessionEvent]:
        """读所有事件(跳过 header 行)。"""
        if not self._path.exists():
            return []
        events: list[SessionEvent] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = _json_loads_safe(line)
                    if obj is None:
                        continue
                    if obj.get("type") == "session":
                        continue
                    try:
                        events.append(SessionEvent.model_validate(obj))
                    except Exception:  # noqa: BLE001
                        logger.debug("skip invalid event line: %r", line[:200])
        except OSError as e:
            logger.warning("read_events failed session=%s: %s", self.session_id, e)
        return events

    # ------------------------------------------------------------------ #
    # 折叠
    # ------------------------------------------------------------------ #

    async def read(self) -> Trajectory:
        """读完整 Trajectory(header + system_prompts + 折叠后的 turns + summary)。"""
        header = await self.read_header()
        events = await self.read_events()

        if header is None:
            # 文件不存在:返回一个 placeholder summary
            return Trajectory(
                session=SessionHeader(
                    id=self.session_id,
                    created_at=0.0,
                ),
                system_prompts=[],
                turns=[],
                summary=TrajectorySummary(
                    turns=0, steps=0, empty=True,
                ),
            )

        system_prompts = _fold_system_prompts(events)
        turns = _fold_to_turns(events)
        summary = _build_summary(turns, empty=False)
        return Trajectory(
            session=header,
            system_prompts=system_prompts,
            turns=turns,
            summary=summary,
        )

    # ------------------------------------------------------------------ #
    # 原始导出
    # ------------------------------------------------------------------ #

    async def read_raw_bytes(self) -> bytes:
        """读 JSONL 原始字节(用于 ``/log/export`` 下载)。"""
        if not self._path.exists():
            return b""
        try:
            with open(self._path, "rb") as f:
                return f.read()
        except OSError as e:
            logger.warning("read_raw_bytes failed session=%s: %s", self.session_id, e)
            return b""


# --------------------------------------------------------------------------- #
# 纯函数:折叠算法
# --------------------------------------------------------------------------- #


def _fold_system_prompts(events: list[SessionEvent]) -> list[SystemPromptRecord]:
    """把扁平事件列表里的 ``system_prompt`` 折叠成 session-level 记录。

    设计要点(参考 deepseek-harness ``request/header`` + ``headerEquals``):
    - chat_service 只在 *首次* (initial) 或 *prompt 真正变化* (change) 时
      写一条 system_prompt 事件
    - 但 **reader 仍做一次内容去重**(相邻 content 相同的折叠成一条):
        * 老 JSONL(早期 chat_service 每 turn 写一次)能正常折叠成 1 条
        * 防止 chat_service 写盘逻辑失效时 UI 重复显示
    - 首条折叠出的记录 reason='initial',后续内容不同的 reason='change'
    - 若 data 里显式带 reason 字段(新 chat_service 写的),尊重 data
    """
    records: list[SystemPromptRecord] = []
    last_content: str | None = None
    for evt in events:
        if evt.type != "system_prompt":
            continue
        d = evt.data or {}
        content = str(d.get("content", ""))
        # 内容跟上一条相同 → 折叠掉(参考 deepseek headerEquals 的"字段相等")
        if last_content is not None and content == last_content:
            continue
        last_content = content

        # 优先用 chat_service 显式给出的 reason;否则按"首/后续"推断
        reason_raw = d.get("reason")
        if reason_raw == "change":
            reason: Literal["initial", "change"] = "change"
        elif reason_raw == "initial":
            reason = "initial"
        else:
            # 老数据无 reason 字段:第一条视为 initial,后续视为 change
            reason = "initial" if not records else "change"

        records.append(
            SystemPromptRecord(
                seq=evt.seq,
                time=evt.time,
                content=content,
                reason=reason,
            )
        )
    return records


def _fold_to_turns(events: list[SessionEvent]) -> list[TrajectoryTurn]:
    """把扁平事件列表折叠成 turns。

    算法:
      - turn_start → 开新 turn,记录 started_at + user_message(后续由
        user_message 事件填充)
      - system_prompt → 忽略(在 ``_fold_system_prompts`` 里处理成 session-level
        记录,不混进 turn.steps)
      - 同一 turn 内累积 ``(turn, step)`` group:
          - assistant_chunk → content += delta
          - assistant_message → 替换 content,记录 usage
          - tool_call → 开 tool 组,等 tool_result 配对
          - tool_result → 收尾 tool 组
          - file_emitted → 独立 step
      - turn_end → 收尾 turn(标记 ended_at / ended_reason;此时合并已有
        steps 与新生成的 assistant/tool steps,统一排序+重新编号)

    turn 编号:**不读 JSONL 的 turn 字段**,而是按 turn_start 出现的顺序重新
    编号(0, 1, 2, ...)。这样可兼容早期 chat_service 硬编码 turn=0 写入的
    历史数据,多轮对话一定能正确区分。
    """
    turns: list[TrajectoryTurn] = []
    current: TrajectoryTurn | None = None
    current_turn_index: int = -1  # fold 时递增的 turn 号

    # 当前 turn 内累积状态
    assistant_acc: dict[tuple[int, int], dict[str, Any]] = {}
    pending_tool: dict[str, dict[str, Any]] = {}

    for evt in events:
        et: SessionEventType = evt.type  # type: ignore[assignment]
        d = evt.data

        if et == "turn_start":
            current_turn_index += 1
            current = TrajectoryTurn(
                turn=current_turn_index,  # 重新编号,不读 JSONL
                started_at=evt.time,
            )
            turns.append(current)
            assistant_acc.clear()
            pending_tool.clear()

        elif et == "system_prompt":
            # system_prompt 是 session-level 事件,在 _fold_system_prompts 里
            # 折叠到 Trajectory.system_prompts,不再混进 turn.steps。
            # (deepseek 设计:只在 initial / change 时记录一次,不每 turn 重复)
            pass

        elif et == "user_message":
            if current is not None:
                content = str(d.get("content", ""))
                current.user_message = content

        elif et == "assistant_chunk":
            turn = current_turn_index
            step = int(d.get("step", 0))
            delta = str(d.get("delta", ""))
            key = (turn, step)
            acc = assistant_acc.setdefault(
                key,
                {
                    "content": "",
                    "input_tokens": None,
                    "output_tokens": None,
                    "started_at": evt.time,
                    "ended_at": None,
                },
            )
            acc["content"] += delta
            acc["ended_at"] = evt.time

        elif et == "assistant_message":
            turn = current_turn_index
            step = int(d.get("step", 0))
            key = (turn, step)
            acc = assistant_acc.setdefault(
                key,
                {
                    "content": "",
                    "input_tokens": None,
                    "output_tokens": None,
                    "started_at": evt.time,
                    "ended_at": evt.time,
                },
            )
            content = str(d.get("content", ""))
            if not acc["content"] or len(content) > len(acc["content"]):
                acc["content"] = content
            usage = d.get("usage") or {}
            if isinstance(usage, dict):
                if usage.get("input_tokens") is not None:
                    acc["input_tokens"] = int(usage["input_tokens"])
                if usage.get("output_tokens") is not None:
                    acc["output_tokens"] = int(usage["output_tokens"])
            acc["ended_at"] = evt.time

        elif et == "tool_call":
            call_id = str(d.get("call_id", ""))
            pending_tool[call_id] = {
                "call_id": call_id,
                "name": str(d.get("name", "")),
                "input": d.get("input") or {},
                "output": "",
                "is_error": False,
                "started_at": evt.time,
                "ended_at": None,
            }

        elif et == "tool_result":
            call_id = str(d.get("call_id", ""))
            tc = pending_tool.get(call_id)
            if tc is None:
                # 没收到对应的 tool_call(理论上不该发生);补一个占位
                tc = {
                    "call_id": call_id,
                    "name": str(d.get("name", "")),
                    "input": {},
                    "output": "",
                    "is_error": False,
                    "started_at": evt.time,
                    "ended_at": evt.time,
                }
                pending_tool[call_id] = tc
            tc["output"] = str(d.get("output", ""))
            tc["is_error"] = bool(d.get("is_error", False))
            tc["ended_at"] = evt.time

        elif et == "file_emitted":
            if current is None:
                continue
            step_idx = len(current.steps)
            current.steps.append(
                TrajectoryStep(
                    turn=current.turn,
                    step=step_idx,
                    kind="file",
                    started_at=evt.time,
                    ended_at=evt.time,
                    file_meta={
                        "url": d.get("url"),
                        "filename": d.get("filename"),
                        "mime": d.get("mime"),
                        "size_bytes": d.get("size_bytes"),
                    },
                )
            )

        elif et == "turn_end":
            if current is not None:
                # 先把累积的 assistant + tool 全部 flush 成 steps
                _flush_steps(
                    current,
                    assistant_acc,
                    pending_tool,
                )
                current.ended_at = evt.time
                current.ended_reason = str(d.get("reason", "normal"))
                current = None

        # session_start / session_end:折叠阶段忽略(已在 header / summary 处理)

    # 兜底:若有 turn 没收到 turn_end,也要 flush
    # 保留 ended_reason = None 表示"未结束"(in-progress 或 process 异常中断)。
    # 真正的 abort 是 chat_service 显式写 turn_end(reason="aborted") 走到的,
    # 不要在这里自动标 "aborted" —— 实时轮询场景下会误把进行中的 turn 渲染成已中断。
    if current is not None:
        _flush_steps(current, assistant_acc, pending_tool)

    return turns


def _flush_steps(
    turn: TrajectoryTurn,
    assistant_acc: dict[tuple[int, int], dict[str, Any]],
    pending_tool: dict[str, dict[str, Any]],
) -> None:
    """把当前 turn 累积状态转成 ``TrajectoryStep`` 列表。

    按 started_at 统一排序,保证 assistant / tool 之间的因果顺序正确
    (例如:assistant 说"让我看一下" → tool 调 ls → assistant 说"找到 2 个文件"
    应该按时间顺序呈现)。

    已有 steps(例如 ``system``)会一起参与排序 + 重新编号,避免 step 字段冲突。
    """
    # 把 turn 已有 step(如 system)与新生成的 assistant/tool 合并,然后统一
    # 排序 + 重新编号,这样 ``step`` 字段不会跟既有内容重复。
    steps: list[TrajectoryStep] = list(turn.steps)

    for key, acc in assistant_acc.items():
        t, s = key
        latency_ms = None
        if acc["started_at"] and acc["ended_at"]:
            latency_ms = int((acc["ended_at"] - acc["started_at"]) * 1000)
        steps.append(
            TrajectoryStep(
                turn=t,
                step=s,
                kind="assistant_message",
                started_at=acc["started_at"],
                ended_at=acc["ended_at"],
                latency_ms=latency_ms,
                assistant=AssistantStep(
                    content=acc["content"],
                    input_tokens=acc["input_tokens"],
                    output_tokens=acc["output_tokens"],
                ),
            )
        )

    for tc in pending_tool.values():
        latency_ms = None
        if tc["started_at"] and tc["ended_at"]:
            latency_ms = int((tc["ended_at"] - tc["started_at"]) * 1000)
        steps.append(
            TrajectoryStep(
                turn=turn.turn,
                step=0,  # 重新编号
                kind="tool",
                started_at=tc["started_at"],
                ended_at=tc["ended_at"],
                latency_ms=latency_ms,
                tool=ToolCallStep(
                    call_id=tc["call_id"],
                    name=tc["name"],
                    input=tc["input"],
                    output=tc["output"],
                    is_error=tc["is_error"],
                    latency_ms=latency_ms,
                ),
            )
        )

    # 统一按 started_at 排序;assistant 在 tool 平局时优先(更符合
    # "LLM 触发工具"的因果直觉)。system_prompt 已不在 steps 里。
    steps.sort(
        key=lambda s: (
            s.started_at or 0,
            0 if s.kind == "assistant_message" else 1,
        )
    )
    # 清空原 steps,把排好序的全部塞回去;同时重新编号 step(从 0 单调递增)
    turn.steps.clear()
    for i, s in enumerate(steps):
        s.step = i
        turn.steps.append(s)


def _build_summary(
    turns: list[TrajectoryTurn],
    empty: bool,
) -> TrajectorySummary:
    """从 turns 汇总 summary。"""
    if empty:
        return TrajectorySummary(turns=0, steps=0, empty=True)

    step_count = sum(len(t.steps) for t in turns)

    # 工具调用统计
    tool_counter: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "error_count": 0})
    for turn in turns:
        for step in turn.steps:
            if step.kind == "tool" and step.tool:
                tool_counter[step.tool.name]["count"] += 1
                if step.tool.is_error:
                    tool_counter[step.tool.name]["error_count"] += 1
    tool_calls = [
        TrajectoryToolCallSummary(
            name=name,
            count=v["count"],
            error_count=v["error_count"],
        )
        for name, v in sorted(tool_counter.items())
    ]

    # token 合计
    total_in = 0
    total_out = 0
    for turn in turns:
        for step in turn.steps:
            if step.kind == "assistant_message" and step.assistant:
                if step.assistant.input_tokens:
                    total_in += step.assistant.input_tokens
                if step.assistant.output_tokens:
                    total_out += step.assistant.output_tokens

    return TrajectorySummary(
        turns=len(turns),
        steps=step_count,
        tool_calls=tool_calls,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        empty=False,
    )