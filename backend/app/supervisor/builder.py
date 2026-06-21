"""DeepAgents Supervisor 装配(@lru_cache 单例)。

state / runtime 设计(基于 deepagents 源码 deepagents/graph.py:236-256):
  - state_schema 不传 → 用 deepagents 默认 DeepAgentState
    (继承 AgentState,messages + jump_to + structured_response,messages 用 DeltaChannel 优化 checkpoint)
  - context_schema=AppContext → 让 tool/middleware 通过 runtime.context.session_id 读取
  - checkpointer=InMemorySaver() → 启用 thread 级 state 持久化
    (state 由 deepagents 内部按 thread_id 自动维护,调用方不传 state)
  - store=InMemoryStore() → 跨 thread 长期记忆(deepagents 不兜底)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from deepagents import create_deep_agent

from app.core.config import get_settings
from app.supervisor.checkpointer import get_checkpointer
from app.supervisor.context import AppContext
from app.supervisor.llm import build_chat_model
from app.supervisor.store import get_store

logger = logging.getLogger(__name__)


def _build_agent() -> Any:
    settings = get_settings()
    llm = build_chat_model(settings.llm)

    # 拉取扩展内容
    from middlewares import ALL_MIDDLEWARES
    from skills import load_skills
    from subagents import ALL_SUBAGENTS

    skills = load_skills("skills")
    logger.info(
        "Loaded %d subagents, %d skills, %d middlewares",
        len(ALL_SUBAGENTS),
        len(skills),
        len(ALL_MIDDLEWARES),
    )

    return create_deep_agent(
        model=llm,
        system_prompt=settings.supervisor_system_prompt,
        subagents=ALL_SUBAGENTS,
        skills=skills,
        middleware=ALL_MIDDLEWARES,
        # state_schema 不传 → DeepAgentState
        context_schema=AppContext,
        checkpointer=get_checkpointer(),
        store=get_store(),
    )


@lru_cache(maxsize=1)
def get_supervisor() -> Any:
    """单例 supervisor(进程内缓存,deepagents 强依赖)。"""
    return _build_agent()


def make_thread_config(thread_id: str) -> dict:
    """绑定 thread_id 用于 stateful 多轮对话。

    注意:state 数据不由调用方传入,而是由 deepagents 内部 checkpointer
    按 thread_id 自动维护;调用方只通过 config.configurable.thread_id 索引。
    """
    return {"configurable": {"thread_id": thread_id}}


__all__ = ["get_supervisor", "make_thread_config"]
