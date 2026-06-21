"""聊天业务:组装消息、调用 supervisor、流式产出事件(dict 透传)。"""

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
from app.supervisor.context import AppContext

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
    user_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """流式生成 deepagents 事件(dict 透传,最后写库 + done)。

    关键:
      - 通过 make_thread_config(session_id) 把调用绑定到 deepagents 的 thread,
        配合 InMemorySaver 实现多轮对话 stateful 记忆(messages/todos/files 自动按 thread_id 持久化)。
      - 通过 context=AppContext(...) 注入运行时业务上下文,供 tool/middleware 读取。
      - 业务库(SQLite)与 LangGraph checkpointer 是两个独立层:
        业务库存展示用历史,checkpointer 存 agent 运行时 state;两者通过 session_id 关联。
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

    # 3. stateful 调用
    agent = get_supervisor()
    config = make_thread_config(session_id)
    context = AppContext(session_id=session_id, user_id=user_id)

    full_text_parts: list[str] = []
    try:
        async for event in agent.astream_events(
            {"messages": lc_messages},
            config=config,
            context=context,
            version="v2",
        ):
            _maybe_collect_token(event, full_text_parts)
            yield event
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


def _maybe_collect_token(event: dict[str, Any], sink: list[str]) -> None:
    """从 on_chat_model_stream 事件中提取增量文本(仅用于持久化,不阻断事件透传)。"""
    if event.get("event") != "on_chat_model_stream":
        return
    chunk = (event.get("data") or {}).get("chunk")
    content = getattr(chunk, "content", None)
    if isinstance(content, str) and content:
        sink.append(content)
