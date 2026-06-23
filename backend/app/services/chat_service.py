"""聊天业务:组装消息、调用 supervisor、流式产出前端 SSE 契约事件。

v5 改动:
  - input 是 delta:只传本轮新增的 [HumanMessage(content=user_message)],
    不再从业务库加载历史、不再拼全量 messages。
  - 历史 messages 由 LangGraph loop 启动时 channels_from_checkpoint
    从 checkpointer 还原,然后 deepagents 的 DeltaChannel._messages_delta_reducer
    按 message.id 去重合并(DeepAgentState.messages: DeltaChannel)。
  - 不传全量 messages 是为了避免 ensure_message_ids 给老消息赋新 UUID,
    污染 checkpoint ID 链,扰乱 tool_call↔tool_message 配对与 summarization tombstone。
  - 业务库(SQLite)与 checkpointer 是两个独立层:业务库存审计/展示,
    checkpointer 存图运行时 state;两者通过 session_id 关联。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.services.session_service import (
    create_default_session,
    rename_if_first_user_message,
)
from app.supervisor.builder import get_supervisor, make_thread_config

logger = logging.getLogger(__name__)


async def ensure_session(
    db: AsyncSession, session_id: str | None, agent_name: str | None
) -> tuple[str, bool]:
    """确保有可用 session,返回 (session_id, 是否新建)。"""
    if session_id:
        existing = await repo.get_session(db, session_id)
        if existing is not None:
            return session_id, False
    new = await create_default_session(db, agent_name=agent_name)
    return new.id, True


async def stream_chat(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    upload_dir: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """流式生成前端 SSE 契约事件(后由 chat.py 渲染为 SSE 行)。

    事件 schema:
      - {"event": "token",      "data": {"content": "<incr>"}}
      - {"event": "tool_call",  "data": {"name": "...", "input": {...}}}
      - {"event": "tool_result","data": {"name": "...", "output": "..."}}
      - {"event": "file",       "data": {"url": "...", "filename": "...", "mime": "..."}}
      - {"event": "done",       "data": {"session_id": "..."}}
      - {"event": "error",      "data": {"message": "..."}}

    upload_dir: 若前端附带(/api/uploads 返回的 upload_dir),会作为
      [UPLOAD_DIR:...] 前缀加到 message 里,让 supervisor 识别为 Excel 流水线。
    """
    # 0. 若有 upload_dir,加 [UPLOAD_DIR:...] 前缀
    llm_message = user_message
    if upload_dir and "[UPLOAD_DIR:" not in user_message:
        llm_message = f"[UPLOAD_DIR:{upload_dir}] {user_message}"

    # 1. 业务库持久化用户消息 + 触发重命名(用原始 user_message,不带前缀)
    await repo.append_message(db, session_id=session_id, role="user", content=user_message)
    await rename_if_first_user_message(db, session_id, user_message)
    await db.commit()

    # 2. 调用 supervisor:input 只传本轮增量 user message。
    #    历史 messages 由 LangGraph 从 checkpointer 还原 + deepagents 的
    #    DeltaChannel._messages_delta_reducer 按 ID 去重合并。
    agent = get_supervisor()
    config = make_thread_config(session_id)
    delta_input = {"messages": [HumanMessage(content=llm_message)]}

    full_text_parts: list[str] = []
    file_emitted = False
    try:
        async for raw in agent.astream_events(
            delta_input,
            config=config,
            version="v2",
        ):
            mapped = _map_event(raw)
            if mapped is None:
                continue
            _collect_text(mapped, full_text_parts)
            # 检测 tool_result 里出现 .xlsx 路径 → 发 file 事件(只发一次)
            if (
                not file_emitted
                and mapped.get("event") == "tool_result"
                and mapped.get("data", {}).get("name") == "write_excel"
            ):
                file_evt = _detect_file_event(mapped["data"].get("output"), session_id)
                if file_evt:
                    yield file_evt
                    file_emitted = True
            yield mapped
    except Exception as e:  # noqa: BLE001
        logger.exception("stream failed")
        yield {"event": "error", "data": {"message": str(e)}}

    # 3. 业务库持久化 assistant 回复 + 发送 done
    full_text = "".join(full_text_parts)
    if full_text:
        await repo.append_message(
            db, session_id=session_id, role="assistant", content=full_text
        )
        await db.commit()
    yield {"event": "done", "data": {"session_id": session_id}}


# --------------------------------------------------------------------------- #
# 事件映射
# --------------------------------------------------------------------------- #


def _map_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """把 deepagents 原生 astream_events(v2) 事件映射为前端 SSE 契约。

    不需要的事件(on_chain_start / on_chain_end / on_chain_stream / metadata /
    on_tool_start 的纯中间件内部事件等)返回 None,调用方直接 continue。
    """
    name = raw.get("event")
    data = raw.get("data") or {}

    if name == "on_chat_model_stream":
        chunk = data.get("chunk")
        content = getattr(chunk, "content", None)
        # 兼容两种 AIMessageChunk.content 形态:
        #   - str: 直接当 token 发
        #   - list[dict]:OpenAI 工具调用增量格式,只把 type=='text' 的段拼成 token
        #     (type=='tool_use' / 'tool_call' 等由 on_tool_* 事件负责,这里不重复)
        if isinstance(content, str) and content:
            return {"event": "token", "data": {"content": content}}
        if isinstance(content, list) and content:
            text = "".join(
                seg.get("text", "")
                for seg in content
                if isinstance(seg, dict) and seg.get("type") == "text"
            )
            if text:
                return {"event": "token", "data": {"content": text}}
        return None

    if name == "on_tool_start":
        return {
            "event": "tool_call",
            "data": {
                "name": data.get("name"),
                "input": data.get("input"),
            },
        }

    if name == "on_tool_end":
        # on_tool_end.output 在不同版本里可能是 ToolMessage / str / dict,
        # 统一尽量序列化为字符串,避免 Pydantic Message 透传到 SSE。
        output = data.get("output")
        if hasattr(output, "content"):
            output_repr = getattr(output, "content", output)
        else:
            output_repr = output
        return {
            "event": "tool_result",
            "data": {
                "name": data.get("name"),
                "output": output_repr,
            },
        }

    # on_chain_start / on_chain_end / on_chain_stream / metadata 等:不下发
    return None


def _collect_text(event: dict[str, Any], sink: list[str]) -> None:
    """从已映射的 token 事件中收集增量文本,用于流结束后写库。"""
    if event.get("event") != "token":
        return
    content = (event.get("data") or {}).get("content")
    if isinstance(content, str) and content:
        sink.append(content)


# .xlsx 路径匹配(同时容忍 /tmp 和 /private/tmp;macOS 上 /tmp 是 symlink,
# resolved 后变 /private/tmp,LLM 写出来的绝对路径会带 /private 前缀)
_XLSX_RE = re.compile(r"((?:/private)?/tmp/swift-agent/[\w\-]+/[^\s\"']+\.xlsx)")


def _detect_file_event(output: Any, session_id: str) -> dict | None:
    """从 write_excel tool_result.output 里提取 xlsx 路径,生成 file 事件。"""
    if output is None:
        return None
    text = str(output)
    m = _XLSX_RE.search(text)
    if not m:
        return None
    xlsx_path = m.group(1)
    p = Path(xlsx_path)
    if not p.exists() or not p.is_file():
        return None
    size = p.stat().st_size
    return {
        "event": "file",
        "data": {
            # 前端调这个 url → 后端 downloads.py 走 FileResponse 返回 xlsx 流
            "url": f"/api/downloads/{session_id}/{p.name}",
            "filename": p.name,
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size_bytes": size,
        },
    }