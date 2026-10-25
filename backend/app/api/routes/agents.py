"""/api/agents 智能体管理 + 智能体市场。

- GET    /api/agents                    列出全部 agent(管理页,展示草稿配置)
- GET    /api/agents/market             只列出已发布的 agent(市场页,展示发布配置)
- POST   /api/agents                    新建 agent
- GET    /api/agents/{id}               agent 详情
- PATCH  /api/agents/{id}               更新 agent(草稿 / 发布配置分开存)
- DELETE /api/agents/{id}               删除 agent
- POST   /api/agents/{id}/default       设为默认 agent
- DELETE /api/agents/{id}/default       取消默认
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db import catalog_repository as cat
from app.schemas.catalog import AgentConfig, AgentCreate, AgentOut, AgentUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_out(obj) -> AgentOut:
    """ORM → Pydantic(config JSON 字段解成结构体)。"""
    return AgentOut(
        id=obj.id,
        name=obj.name,
        draft_config=AgentConfig(**cat.parse_agent_config(obj.draft_config)),
        published_config=AgentConfig(**cat.parse_agent_config(obj.published_config)),
        published=obj.published,
        parent_id=obj.parent_id,
        is_default=obj.is_default,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@router.get("", response_model=list[AgentOut])
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[AgentOut]:
    objs = await cat.list_agents(db)
    return [_to_out(o) for o in objs]


@router.get("/market", response_model=list[AgentOut])
async def list_market_agents(db: AsyncSession = Depends(get_db)) -> list[AgentOut]:
    """智能体市场:只返回已发布的 agent(卡片展示发布配置)。"""
    objs = await cat.list_agents(db, published_only=True)
    return [_to_out(o) for o in objs]


@router.post("", response_model=AgentOut)
async def create_agent(
    body: AgentCreate, db: AsyncSession = Depends(get_db)
) -> AgentOut:
    draft = body.draft_config.model_dump()
    published = body.published_config
    obj = await cat.create_agent(
        db,
        name=body.name,
        draft_config=draft,
        # 建时给了发布配置 → 直接是已发布状态
        published_config=(published.model_dump() if published else None),
        published=published is not None,
        parent_id=body.parent_id,
    )
    await db.commit()
    return _to_out(obj)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> AgentOut:
    obj = await cat.get_agent(db, agent_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _to_out(obj)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db)
) -> AgentOut:
    obj = await cat.get_agent(db, agent_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="agent not found")

    updated = await cat.update_agent(
        db,
        agent_id,
        name=body.name,
        draft_config=(body.draft_config.model_dump() if body.draft_config else None),
        published_config=(
            body.published_config.model_dump() if body.published_config else None
        ),
        published=body.published,
        parent_id=body.parent_id,
    )
    await db.commit()
    return _to_out(updated)


@router.post("/{agent_id}/default", response_model=AgentOut)
async def set_default_agent(
    agent_id: str, db: AsyncSession = Depends(get_db)
) -> AgentOut:
    """设为默认 agent(会话未绑定 agent 时用它)。"""
    obj = await cat.get_agent(db, agent_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="agent not found")
    await cat.set_default_agent(db, agent_id)
    await db.commit()
    return _to_out(await cat.get_agent(db, agent_id))


@router.delete("/{agent_id}/default")
async def unset_default_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    obj = await cat.get_agent(db, agent_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="agent not found")
    await cat.set_default_agent(db, None)
    await db.commit()
    return {"ok": True}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    obj = await cat.get_agent(db, agent_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="agent not found")
    await cat.delete_agent(db, agent_id)
    await db.commit()
    return {"ok": True}
