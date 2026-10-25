"""启动时播种 DB 元数据。

v10:先把已注册的内置工具同步进 tools 表(builtin=True,前端只读)。
播种是幂等的:按 name 查找,已存在则跳过(不覆盖用户改过的内容)。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import catalog_repository as cat
from app.db.models import Tool

logger = logging.getLogger(__name__)


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
