"""聊天业务:组装消息、调用 supervisor、流式产出前端 SSE 契约事件。

v4 改动:把 deepagents 原生 astream_events(v2) 事件
(on_chat_model_stream / on_tool_start / on_tool_end / on_chain_*) 映射为前端
期望的 5 类事件(token / tool_call / tool_result / done / error),
中间链路事件(on_chain_start / on_chain_end / metadata 等)直接丢弃。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
) -> AsyncIterator[dict[str, Any]]:
    """流式生成前端 SSE 契约事件(后由 chat.py 渲染为 SSE 行)。

    事件 schema:
      - {"event": "token",      "data": {"content": "<incr>"}}
      - {"event": "tool_call",  "data": {"name": "...", "input": {...}}}
      - {"event": "tool_result","data": {"name": "...", "output": "..."}}
      - {"event": "done",       "data": {"session_id": "..."}}
      - {"event": "error",      "data": {"message": "..."}}

    关键:
      - 通过 make_thread_config(session_id) 把调用绑定到 deepagents 的 thread,
        配合 InMemorySaver 实现多轮对话 stateful 记忆。
      - 业务库(SQLite)与 LangGraph checkpointer 是两个独立层,通过 session_id 关联。
      - 不传 context(当前阶段无业务 context,Runtime[Context] / ToolRuntime[Context]
        留给后续自定义 middleware 使用)。
    """
    # 1. 持久化用户消息 + 触发重命名
    await repo.append_message(db, session_id=session_id, role="user", content=user_message)
    await rename_if_first_user_message(db, session_id, user_message)
    await db.commit()

    # 2. 加载历史(拼成 LangChain messages)
    history = await repo.list_messages(db, session_id)
    await db.commit()

    lc_messages: list = []
    for m in history:
        if m.role == "user":
            lc_messages.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            lc_messages.append(AIMessage(content=m.content))
        elif m.role == "system":
            lc_messages.append(SystemMessage(content=m.content))

    # 3. stateful 调用 + 事件映射
    agent = get_supervisor()
    config = make_thread_config(session_id)

    full_text_parts: list[str] = []
    try:
        async for raw in agent.astream_events(
            {"messages": lc_messages},
            config=config,
            version="v2",
        ):
            mapped = _map_event(raw)
            if mapped is None:
                continue
            _collect_text(mapped, full_text_parts)
            yield mapped
    except Exception as e:  # noqa: BLE001
        logger.exception("stream failed")
        yield {"event": "error", "data": {"message": str(e)}}

    # 4. 写库并发送 done
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
        if isinstance(content, str) and content:
            return {"event": "token", "data": {"content": content}}
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