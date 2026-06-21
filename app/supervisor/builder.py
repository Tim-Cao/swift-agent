"""DeepAgents Supervisor 装配(@lru_cache 单例)。

按设计从四个扩展目录拉取内容,装配成 create_deep_agent(...)。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.supervisor.llm import build_chat_openai

logger = logging.getLogger(__name__)


def _build_agent() -> Any:
    """真实构造 supervisor agent(失败时返回 None)。"""
    settings = get_settings()

    # LLM
    llm = build_chat_openai(settings.llm)

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

    try:
        from deepagents import create_deep_agent
    except ImportError as e:
        logger.warning("deepagents not installed: %s", e)
        return None

    # create_deep_agent 在不同版本中参数名略有差异,这里做兼容
    kwargs: dict[str, Any] = {
        "model": llm,
        "system_prompt": settings.supervisor_system_prompt,
    }
    if ALL_SUBAGENTS:
        kwargs["subagents"] = ALL_SUBAGENTS
    if skills:
        kwargs["skills"] = skills
    if ALL_MIDDLEWARES:
        # middlewares vs middleware 兼容
        try:
            return create_deep_agent(**kwargs, middlewares=ALL_MIDDLEWARES)
        except TypeError:
            return create_deep_agent(**kwargs, middleware=ALL_MIDDLEWARES)

    return create_deep_agent(**kwargs)


@lru_cache(maxsize=1)
def get_supervisor() -> Any:
    """单例 supervisor(进程内缓存)。"""
    return _build_agent()
