"""仓储层:Agent / Tool / Provider / Model 的 CRUD。

与 repository.py(Session / Message)分开,避免单文件过长。

v11:agent 的工具绑定不再走关联表,而是存在 ``draft_config`` /
``published_config`` 两个 JSON 字段里(``tool_ids`` 列表)。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Agent, MCPServer, Model, Provider, Tool


# ---------- Tool ----------


async def list_tools(db: AsyncSession, *, builtin: bool | None = None) -> list[Tool]:
    stmt = select(Tool)
    if builtin is not None:
        stmt = stmt.where(Tool.builtin == builtin)
    result = await db.execute(stmt.order_by(Tool.builtin.desc(), Tool.name))
    return list(result.scalars())


async def get_tool(db: AsyncSession, tool_id: str) -> Tool | None:
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    return result.scalar_one_or_none()


async def get_tool_by_name(db: AsyncSession, name: str) -> Tool | None:
    result = await db.execute(select(Tool).where(Tool.name == name))
    return result.scalar_one_or_none()


async def create_tool(
    db: AsyncSession,
    *,
    name: str,
    display_name: str,
    description: str,
    builtin: bool = False,
    source_dir: str | None = None,
) -> Tool:
    obj = Tool(
        name=name,
        display_name=display_name or name,
        description=description,
        builtin=builtin,
        source_dir=source_dir,
    )
    db.add(obj)
    await db.flush()
    return obj


async def update_tool(
    db: AsyncSession,
    tool_id: str,
    *,
    display_name: str | None = None,
    description: str | None = None,
    name: str | None = None,
) -> Tool | None:
    obj = await get_tool(db, tool_id)
    if obj is None:
        return None
    if display_name is not None:
        obj.display_name = display_name
    if description is not None:
        obj.description = description
    if name is not None:
        obj.name = name
    obj.updated_at = datetime.utcnow()
    await db.flush()
    return obj


async def delete_tool(db: AsyncSession, tool_id: str) -> bool:
    obj = await get_tool(db, tool_id)
    if obj is None:
        return False
    await db.delete(obj)
    await db.flush()
    return True


# ---------- Agent ----------


# agent config JSON 的标准结构:{"system_prompt": str, "tool_ids": list[str]}
def empty_agent_config() -> dict[str, Any]:
    return {"system_prompt": "", "tool_ids": []}


def parse_agent_config(raw: str | None) -> dict[str, Any]:
    """把 config JSON 字符串解成 dict;解析失败回落到空配置。"""
    if not raw:
        return empty_agent_config()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return empty_agent_config()
    if not isinstance(data, dict):
        return empty_agent_config()
    return {
        "system_prompt": str(data.get("system_prompt") or ""),
        "tool_ids": [str(t) for t in (data.get("tool_ids") or [])],
    }


def dump_agent_config(config: dict[str, Any] | None) -> str:
    """把 config dict 序列化成 JSON 字符串(只保留已知字段)。"""
    cfg = config or {}
    payload = {
        "system_prompt": str(cfg.get("system_prompt") or ""),
        "tool_ids": [str(t) for t in (cfg.get("tool_ids") or [])],
    }
    return json.dumps(payload, ensure_ascii=False)


def _agent_stmt():
    return select(Agent).options(selectinload(Agent.children))


async def _reload_agent(db: AsyncSession, agent_id: str) -> Agent | None:
    """重新加载 agent(带 children 关系)。

    create/update 之后必须走这条路:ORM 对象的 children 关系在异步模式下是
    lazy-load,直接访问会抛 MissingGreenlet(在 greenlet 上下文外做 IO)。
    """
    result = await db.execute(_agent_stmt().where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def list_agents(
    db: AsyncSession, *, published_only: bool = False, top_level_only: bool = False
) -> list[Agent]:
    stmt = _agent_stmt()
    if published_only:
        stmt = stmt.where(Agent.published.is_(True))
    if top_level_only:
        stmt = stmt.where(Agent.parent_id.is_(None))
    result = await db.execute(stmt.order_by(Agent.name))
    return list(result.scalars())


async def get_agent(db: AsyncSession, agent_id: str) -> Agent | None:
    result = await db.execute(_agent_stmt().where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def get_agent_by_name(db: AsyncSession, name: str) -> Agent | None:
    result = await db.execute(_agent_stmt().where(Agent.name == name))
    return result.scalar_one_or_none()


async def create_agent(
    db: AsyncSession,
    *,
    name: str,
    draft_config: dict[str, Any] | None = None,
    published_config: dict[str, Any] | None = None,
    published: bool = False,
    parent_id: str | None = None,
    is_default: bool = False,
) -> Agent:
    obj = Agent(
        name=name,
        draft_config=dump_agent_config(draft_config),
        published_config=dump_agent_config(published_config),
        published=published,
        parent_id=parent_id,
        is_default=is_default,
    )
    db.add(obj)
    await db.flush()
    return await _reload_agent(db, obj.id)


async def update_agent(
    db: AsyncSession,
    agent_id: str,
    *,
    name: str | None = None,
    draft_config: dict[str, Any] | None = None,
    published_config: dict[str, Any] | None = None,
    published: bool | None = None,
    parent_id: str | None = None,
) -> Agent | None:
    obj = await get_agent(db, agent_id)
    if obj is None:
        return None
    if name is not None:
        obj.name = name
    if draft_config is not None:
        obj.draft_config = dump_agent_config(draft_config)
    if published_config is not None:
        obj.published_config = dump_agent_config(published_config)
    if published is not None:
        obj.published = published
    if parent_id is not None:
        obj.parent_id = parent_id
    obj.updated_at = datetime.utcnow()
    await db.flush()
    return await _reload_agent(db, agent_id)


async def set_default_agent(db: AsyncSession, agent_id: str | None) -> None:
    """设置全局默认 agent(整个系统只有一个)。"""
    await db.execute(update(Agent).values(is_default=False))
    if agent_id:
        obj = await get_agent(db, agent_id)
        if obj is not None:
            obj.is_default = True
            obj.updated_at = datetime.utcnow()
    await db.flush()


async def get_default_agent(db: AsyncSession) -> Agent | None:
    result = await db.execute(select(Agent).where(Agent.is_default.is_(True)).limit(1))
    return result.scalar_one_or_none()


async def delete_agent(db: AsyncSession, agent_id: str) -> bool:
    obj = await get_agent(db, agent_id)
    if obj is None:
        return False
    await db.delete(obj)
    await db.flush()
    return True


# ---------- Provider ----------


async def list_providers(db: AsyncSession) -> list[Provider]:
    result = await db.execute(
        select(Provider).options(selectinload(Provider.models)).order_by(Provider.name)
    )
    return list(result.scalars())


async def get_provider(db: AsyncSession, provider_id: str) -> Provider | None:
    result = await db.execute(
        select(Provider).options(selectinload(Provider.models)).where(Provider.id == provider_id)
    )
    return result.scalar_one_or_none()


async def get_provider_by_slug(db: AsyncSession, slug: str) -> Provider | None:
    """按「提供商 ID」取记录。"""
    result = await db.execute(
        select(Provider).options(selectinload(Provider.models)).where(Provider.slug == slug)
    )
    return result.scalar_one_or_none()


async def create_provider(
    db: AsyncSession,
    *,
    name: str,
    base_url: str,
    slug: str = "",
    api_key: str = "",
    enabled: bool = True,
) -> Provider:
    # slug 有 unique 约束,空串只能有一个 —— 兜底生成一个,免得直接撞约束报错
    if not slug:
        from app.core.slugify import slugify

        slug = slugify(name) or "provider"
    obj = Provider(
        name=name, slug=slug, base_url=base_url, api_key=api_key, enabled=enabled
    )
    db.add(obj)
    await db.flush()
    return obj


async def update_provider(
    db: AsyncSession,
    provider_id: str,
    *,
    name: str | None = None,
    slug: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enabled: bool | None = None,
    default_model_id: str | None = None,
) -> Provider | None:
    obj = await get_provider(db, provider_id)
    if obj is None:
        return None
    if name is not None:
        obj.name = name
    if slug is not None:
        obj.slug = slug
    if base_url is not None:
        obj.base_url = base_url
    if api_key is not None:
        obj.api_key = api_key
    if enabled is not None:
        obj.enabled = enabled
    if default_model_id is not None:
        obj.default_model_id = default_model_id
    obj.updated_at = datetime.utcnow()
    await db.flush()
    return obj


async def delete_provider(db: AsyncSession, provider_id: str) -> bool:
    obj = await get_provider(db, provider_id)
    if obj is None:
        return False
    await db.delete(obj)
    await db.flush()
    return True


# ---------- Model ----------


async def list_models(db: AsyncSession) -> list[Model]:
    result = await db.execute(select(Model).order_by(Model.id))
    return list(result.scalars())


async def get_model(db: AsyncSession, model_id: str) -> Model | None:
    result = await db.execute(select(Model).where(Model.id == model_id))
    return result.scalar_one_or_none()


async def upsert_models(
    db: AsyncSession,
    provider_id: str,
    model_ids: Sequence[str],
    *,
    display_names: dict[str, str] | None = None,
) -> list[Model]:
    """把提供商发现的模型同步进 DB(新增 + 更新显示名,不删除历史项)。

    返回本轮写入的 Model 列表。
    """
    names = display_names or {}
    out: list[Model] = []
    for mid in model_ids:
        obj = await get_model(db, mid)
        if obj is None:
            obj = Model(
                id=mid,
                provider_id=provider_id,
                display_name=names.get(mid, mid),
            )
            db.add(obj)
        else:
            obj.provider_id = provider_id
            if names.get(mid):
                obj.display_name = names[mid]
            obj.updated_at = datetime.utcnow()
        await db.flush()
        out.append(obj)
    return out


async def set_default_model(db: AsyncSession, model_id: str | None) -> None:
    """设置全局默认模型(整个系统只有一个)。"""
    await db.execute(update(Model).values(is_default=False))
    if model_id:
        obj = await get_model(db, model_id)
        if obj is not None:
            obj.is_default = True
            obj.updated_at = datetime.utcnow()
    await db.flush()


async def get_default_model(db: AsyncSession) -> Model | None:
    result = await db.execute(select(Model).where(Model.is_default.is_(True)).limit(1))
    return result.scalar_one_or_none()


__all__ = [
    "list_tools",
    "get_tool",
    "get_tool_by_name",
    "create_tool",
    "update_tool",
    "delete_tool",
    "list_agents",
    "get_agent",
    "get_agent_by_name",
    "create_agent",
    "update_agent",
    "set_default_agent",
    "get_default_agent",
    "delete_agent",
    "empty_agent_config",
    "parse_agent_config",
    "dump_agent_config",
    "list_providers",
    "get_provider",
    "get_provider_by_slug",
    "create_provider",
    "update_provider",
    "delete_provider",
    "list_models",
    "get_model",
    "upsert_models",
    "set_default_model",
    "get_default_model",
    "list_mcp_servers",
    "get_mcp_server",
    "get_mcp_server_by_name",
    "create_mcp_server",
    "update_mcp_server",
    "delete_mcp_server",
]


# ---------- MCP Server ----------


async def list_mcp_servers(db: AsyncSession) -> list[MCPServer]:
    result = await db.execute(select(MCPServer).order_by(MCPServer.name))
    return list(result.scalars())


async def get_mcp_server(db: AsyncSession, server_id: str) -> MCPServer | None:
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    return result.scalar_one_or_none()


async def get_mcp_server_by_name(db: AsyncSession, name: str) -> MCPServer | None:
    result = await db.execute(select(MCPServer).where(MCPServer.name == name))
    return result.scalar_one_or_none()


async def create_mcp_server(
    db: AsyncSession,
    *,
    name: str,
    transport: str,
    config_json: str = "{}",
    tool_names: str = "[]",
    enabled: bool = True,
) -> MCPServer:
    obj = MCPServer(
        name=name,
        transport=transport,
        config_json=config_json,
        tool_names=tool_names,
        enabled=enabled,
    )
    db.add(obj)
    await db.flush()
    return obj


async def update_mcp_server(
    db: AsyncSession,
    server_id: str,
    *,
    name: str | None = None,
    transport: str | None = None,
    config_json: str | None = None,
    tool_names: str | None = None,
    status: str | None = None,
    status_detail: str | None = None,
    enabled: bool | None = None,
) -> MCPServer | None:
    obj = await get_mcp_server(db, server_id)
    if obj is None:
        return None
    if name is not None:
        obj.name = name
    if transport is not None:
        obj.transport = transport
    if config_json is not None:
        obj.config_json = config_json
    if tool_names is not None:
        obj.tool_names = tool_names
    if status is not None:
        obj.status = status
    if status_detail is not None:
        obj.status_detail = status_detail
    if enabled is not None:
        obj.enabled = enabled
    obj.updated_at = datetime.utcnow()
    await db.flush()
    return obj


async def delete_mcp_server(db: AsyncSession, server_id: str) -> bool:
    obj = await get_mcp_server(db, server_id)
    if obj is None:
        return False
    await db.delete(obj)
    await db.flush()
    return True
