"""聊天业务逻辑:组装消息、调用 supervisor、流式产出事件。"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.schemas.chat import StreamEvent
from app.services.session_service import create_default_session, rename_if_first_user_message

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
) -> AsyncIterator[StreamEvent]:
    """流式生成 SSE 事件。

    实现策略:
      1. 读取历史消息(拼成 LangChain messages)
      2. 调 supervisor graph.stream(...)
      3. 逐 token 产出,最后写库并发送 done
    """
    # 1. 持久化用户消息 + 触发重命名
    await repo.append_message(db, session_id=session_id, role="user", content=user_message)
    await rename_if_first_user_message(db, session_id, user_message)
    await db.commit()

    # 2. 加载历史
    history = await repo.list_messages(db, session_id)
    await db.commit()

    # 3. 调用 supervisor
    try:
        from app.supervisor.builder import get_supervisor

        agent = get_supervisor()
    except Exception as e:  # noqa: BLE001
        logger.exception("supervisor build failed")
        yield StreamEvent(type="error", content=f"supervisor unavailable: {e}")
        return

    # 4. 组装 LangChain messages
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        lc_messages: list = []
        for m in history:
            if m.role == "user":
                lc_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                lc_messages.append(AIMessage(content=m.content))
            elif m.role == "system":
                lc_messages.append(SystemMessage(content=m.content))
    except ImportError:
        lc_messages = [{"role": m.role, "content": m.content} for m in history]

    # 5. 流式调用
    full_text_parts: list[str] = []
    try:
        if agent is None:
            # deepagents 未安装,降级为 echo
            yield StreamEvent(type="token", content=f"[echo] {user_message}")
            full_text_parts.append(user_message)
        else:
            try:
                stream_iter = agent.stream(
                    {"messages": lc_messages}, stream_mode="messages"
                )
            except TypeError:
                stream_iter = agent.stream({"messages": lc_messages})

            async for chunk in _aiter(stream_iter):  # type: ignore[arg-type]
                token = _extract_token(chunk)
                if token:
                    full_text_parts.append(token)
                    yield StreamEvent(type="token", content=token)
    except Exception as e:  # noqa: BLE001
        logger.exception("stream failed")
        yield StreamEvent(type="error", content=str(e))

    # 6. 写库并发送 done
    full_text = "".join(full_text_parts)
    if full_text:
        await repo.append_message(db, session_id=session_id, role="assistant", content=full_text)
        await db.commit()
    yield StreamEvent(type="done", meta={"session_id": session_id})


# ---------- helpers ----------

async def _aiter(it):  # type: ignore[no-untyped-def]
    """把 sync iterable 转 async(支持 async iterable)。"""
    if hasattr(it, "__aiter__"):
        async for x in it:
            yield x
        return
    for x in it:
        yield x


def _extract_token(chunk: Any) -> str | None:
    """从 langgraph chunk 中提取增量 token 文本。"""
    # 多种 chunk 形态兼容
    try:
        # tuple(node_name, message)
        if isinstance(chunk, tuple) and len(chunk) == 2:
            chunk = chunk[1]
        # AIMessageChunk
        content = getattr(chunk, "content", None)
        if isinstance(content, str) and content:
            return content
        # dict 形态
        if isinstance(chunk, dict):
            if "messages" in chunk:
                msgs = chunk["messages"]
                if isinstance(msgs, list) and msgs:
                    return _extract_token(msgs[-1])
            token = chunk.get("token") or chunk.get("content")
            if isinstance(token, str) and token:
                return token
    except Exception:  # noqa: BLE001
        return None
    return None
