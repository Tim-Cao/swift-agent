"""启动时播种 DB 元数据。

v10:先把已注册的内置工具同步进 tools 表(builtin=True,前端只读)。
v11.3:再把 .mcp.json 里的 MCP server 播种进 mcp_servers 表,
之后由「MCP 管理」页维护。
播种是幂等的:按 name 查找,已存在则跳过(不覆盖用户改过的内容)。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import catalog_repository as cat
from app.db.models import MCPServer, Tool

logger = logging.getLogger(__name__)

# 播种 MCP 用的默认配置来源:backend/.mcp.json
_MCP_CONFIG_PATH = Path(__file__).resolve().parents[2] / ".mcp.json"


async def seed_tools(db: AsyncSession) -> list[Tool]:
    """把已注册的内置工具同步进 tools 表。

    只处理 builtin=True 的:用户上传的工具记录由上传流程自己写,不动。
    """
    # import 触发注册
    from tools import excel_pipeline  # noqa: F401
    from tools import list_tool_meta

    out: list[Tool] = []
    for meta in list_tool_meta():
        if not meta.builtin:
            continue
        existing = await cat.get_tool_by_name(db, meta.name)
        if existing is None:
            obj = await cat.create_tool(
                db,
                name=meta.name,
                display_name=meta.display_name,
                description=meta.description,
                builtin=True,
                source_dir=None,
            )
            logger.info("[seed] 新增内置工具 %s", meta.name)
        else:
            # 内置工具的显示名 / 描述跟着代码走
            existing.display_name = meta.display_name
            existing.description = meta.description
            existing.builtin = True
            obj = existing
        out.append(obj)
    await db.flush()
    return out


async def _tool_ids_for(db: AsyncSession, tool_names: list[str]) -> list[str]:
    """按工具注册名换出 tool id(找不到的跳过)。"""
    ids: list[str] = []
    for name in tool_names:
        t = await cat.get_tool_by_name(db, name)
        if t is not None:
            ids.append(t.id)
        else:
            logger.warning("[seed] 工具 %s 未注册,跳过绑定", name)
    return ids


async def seed_all(db: AsyncSession) -> None:
    """播种全部元数据(幂等)。"""
    tools = await seed_tools(db)
    mcp_servers = await seed_mcp_servers(db)
    await db.commit()
    logger.info(
        "[seed] 元数据就绪: %d 个工具, %d 个 MCP",
        len(tools),
        len(mcp_servers),
    )


# ---------- MCP Server ----------

# .mcp.json 里的 key 是老式的下划线名字,页面里用包名更直观。
_MCP_NAME_OVERRIDES = {
    "minimax_coding_plan": "minimax-coding-plan-mcp",
}


def _env_to_ref(env: dict) -> dict:
    """把跟环境变量同值的 env 条目改写成 ``${VAR}`` 引用。

    不在库里存明文密钥 —— 值跟某个环境变量一样时,只存引用。
    """
    import os

    out: dict[str, str] = {}
    for k, v in (env or {}).items():
        if not isinstance(v, str):
            continue
        ref = f"${{{k}}}"
        if os.environ.get(k) == v:
            out[k] = ref
        else:
            out[k] = v
    return out


async def seed_mcp_servers(db: AsyncSession) -> list[MCPServer]:
    """把 .mcp.json 里的 server 播种进 mcp_servers 表。

    幂等:按 name 查找,已存在则跳过(用户在页面上改过的配置不覆盖)。
    .mcp.json 不存在或为空时什么都不做。
    """
    from app.services.mcp_config import from_client_config

    if not _MCP_CONFIG_PATH.exists():
        return []
    try:
        with _MCP_CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        logger.warning("[seed] .mcp.json 读取失败: %s", e)
        return []

    servers = data.get("mcpServers") or {}
    if not servers:
        return []

    out: list[MCPServer] = []
    for key, cfg in servers.items():
        name = _MCP_NAME_OVERRIDES.get(key, key)
        if await cat.get_mcp_server_by_name(db, name) is not None:
            continue
        transport, config = from_client_config(name, cfg)
        if isinstance(config.get("env"), dict):
            config["env"] = _env_to_ref(config["env"])
        obj = await cat.create_mcp_server(
            db,
            name=name,
            transport=transport,
            config_json=json.dumps(config, ensure_ascii=False),
            enabled=True,
        )
        out.append(obj)
        logger.info("[seed] 新增 MCP %s (transport=%s)", name, transport)
    await db.flush()
    return out


__all__ = ["seed_tools", "seed_mcp_servers", "seed_all"]
