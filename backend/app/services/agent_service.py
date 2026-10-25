"""把 DB 里的 agent 记录解析成可运行的 deepagents agent。

v11:
  - agent 的提示词 / 工具绑定存在 ``draft_config`` / ``published_config``
    两份 JSON 里;已发布用 published_config,未发布用 draft_config
  - 子 agent(``parent_id`` 非空)转成 deepagents 的 ``subagents=`` 参数
  - 模型:统一用「被标记为默认的模型」(models.is_default=True)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import catalog_repository as cat
from app.db.models import Agent, Tool

logger = logging.getLogger(__name__)


async def _tool_instances(db: AsyncSession, tool_ids: list[str]) -> list[Any]:
    """把 config 里的 tool id 列表换成工具实例。

    tools 表的 id 是 uuid,工具的**注册名**是 name —— TOOLKIT 按注册名索引,
    所以这里先 id→name 查表,再按注册名取实例。
    """
    if not tool_ids:
        return []
    result = await db.execute(select(Tool).where(Tool.id.in_(list(tool_ids))))
    tools = list(result.scalars())
    names = [t.name for t in tools]
    # 允许 config 直接写注册名(向后兼容 / 手改 DB)
    for tid in tool_ids:
        if tid not in {t.id for t in tools}:
            names.append(tid)

    from tools import get_tools

    return get_tools(names)


async def resolve_model(
    db: AsyncSession,
) -> tuple[Any | None, Any | None]:
    """取「被标记为默认的模型」及其提供商。没有则返回 (None, None)。"""
    model = await cat.get_default_model(db)
    if model is None:
        return None, None
    provider = await cat.get_provider(db, model.provider_id)
    return model, provider


def _subagent_description(system_prompt: str) -> str:
    """从 system_prompt 取首行当 description。

    DB 里没有独立的 description 字段,但 deepagents 的 subagent spec 必须有
    description(父 agent 靠它决定何时委派)。播种时把原 description 放在了
    system_prompt 第一行,所以这里取首行即可。
    """
    for line in (system_prompt or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


async def build_subagent_specs(
    db: AsyncSession, parent: Agent
) -> list[dict[str, Any]]:
    """把 parent 的子 agent 转成 deepagents 的 subagents= 参数。"""
    children = [c for c in (parent.children or []) if c.id != parent.id]
    if not children:
        return []

    specs: list[dict[str, Any]] = []
    for child in children:
        cfg = cat.parse_agent_config(
            child.published_config if child.published else child.draft_config
        )
        tools = await _tool_instances(db, cfg.get("tool_ids", []))
        spec: dict[str, Any] = {
            "name": child.name,
            "description": _subagent_description(cfg.get("system_prompt", "")),
            "system_prompt": cfg.get("system_prompt", ""),
        }
        if tools:
            spec["tools"] = tools
        specs.append(spec)
    return specs


async def resolve_agent_for_session(
    db: AsyncSession, session_id: str
) -> Any | None:
    """按会话绑定的 agent_id 构建 agent;没有绑定则用默认 agent。

    会话没绑 agent → 找 ``is_default=True`` 的 agent;也没有 → 返回 None
    (调用方再退回到「无 agent 的裸 supervisor」)。
    """
    from app.db import repository as repo
    from app.supervisor.agent_runtime import build_agent

    session = await repo.get_session(db, session_id)
    agent_rec: Agent | None = None
    if session is not None and session.agent_id:
        agent_rec = await cat.get_agent(db, session.agent_id)
        if agent_rec is None:
            logger.warning(
                "session %s 绑定的 agent %s 不存在,回退默认 agent",
                session_id,
                session.agent_id,
            )
    if agent_rec is None:
        agent_rec = await cat.get_default_agent(db)
    if agent_rec is None:
        return None

    return await build_agent_from_record(db, agent_rec)


async def build_agent_from_record(db: AsyncSession, agent_rec: Agent) -> Any:
    """按一条 agent 记录构建可运行的 agent(含子 agent / 工具 / 默认模型)。"""
    from app.supervisor.agent_runtime import build_agent

    cfg = cat.parse_agent_config(
        agent_rec.published_config if agent_rec.published else agent_rec.draft_config
    )
    tools = await _tool_instances(db, cfg.get("tool_ids", []))
    subagents = await build_subagent_specs(db, agent_rec)
    model, provider = await resolve_model(db)

    # 中间件:复用 WebSearchGate 等项目中间件(每次构建一份,避免跨 agent 串味)
    from middlewares import build_middlewares

    return build_agent(
        name=agent_rec.name,
        system_prompt=cfg.get("system_prompt", ""),
        tools=tools,
        subagents=subagents,
        model=model,
        provider=provider,
        middleware=build_middlewares(),
        checkpointer=_get_checkpointer(),
        store=_get_store(),
    )


def _get_checkpointer() -> Any:
    from app.supervisor.checkpointer import get_checkpointer

    return get_checkpointer()


def _get_store() -> Any:
    from app.supervisor.store import get_store

    return get_store()


__all__ = [
    "resolve_agent_for_session",
    "build_agent_from_record",
    "build_subagent_specs",
    "resolve_model",
]
