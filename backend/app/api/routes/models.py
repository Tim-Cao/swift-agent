"""/api/providers + /api/models 模型管理。

提供商(可配置):
- GET    /api/providers                  列出提供商
- POST   /api/providers                  新增提供商
- PATCH  /api/providers/{id}             修改提供商
- DELETE /api/providers/{id}             删除提供商
- POST   /api/providers/{id}/discover    通过 /models 接口发现可用模型

模型:
- GET    /api/models                     列出模型(带 is_default)
- POST   /api/models/{id}/default        设为默认模型
- DELETE /api/models/{id}/default        取消默认
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.slugify import slugify
from app.db import catalog_repository as cat
from app.db.models import Provider
from app.schemas.catalog import (
    ModelDiscoveryResult,
    ModelOut,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
)
from app.services.model_discovery import ModelDiscoveryError, discover_models

logger = logging.getLogger(__name__)
providers_router = APIRouter()
models_router = APIRouter()


def _provider_to_out(obj) -> ProviderOut:
    return ProviderOut(
        id=obj.id,
        name=obj.name,
        slug=obj.slug,
        base_url=obj.base_url,
        # API Key 只回传掩码,避免明文进前端日志
        api_key=_mask(obj.api_key),
        enabled=obj.enabled,
        default_model_id=obj.default_model_id,
        model_ids=[m.id for m in obj.models],
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


async def _unique_slug(
    db: AsyncSession, raw: str, *, fallback: str, exclude_id: str | None = None
) -> str:
    """把用户填的「提供商 ID」规整成唯一值。

    - 规整成小写 + 短横线(``slugify``)
    - 空的话用 ``fallback``(一般是名称)兜底
    - 撞了就加 ``-2`` / ``-3`` 后缀
    """
    base = slugify(raw) or slugify(fallback) or "provider"
    candidate = base
    n = 1
    while True:
        existing = await cat.get_provider_by_slug(db, candidate)
        if existing is None or (exclude_id and existing.id == exclude_id):
            return candidate
        n += 1
        candidate = f"{base}-{n}"


def _mask(key: str) -> str:
    """API Key 掩码:保留前 4 位与后 2 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 6)}{key[-2:]}"


def _is_mask(value: str) -> bool:
    """判断一个字符串是不是掩码(而不是真 key)。

    掩码形如 ``sk-a**********89`` —— 中间是一串连续的 ``*``。
    旧逻辑只判 ``startswith("***")``,但掩码保留前 4 位,所以永远不以 ``*`` 开头,
    那个判断等于没生效:把掩码原样回传会被当成新 key 存进 DB,把真 key 覆盖掉。
    """
    if not value:
        return False
    return "***" in value


# ---------- Provider ----------


@providers_router.get("", response_model=list[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_db)) -> list[ProviderOut]:
    objs = await cat.list_providers(db)
    return [_provider_to_out(o) for o in objs]


@providers_router.post("", response_model=ProviderOut)
async def create_provider(
    body: ProviderCreate, db: AsyncSession = Depends(get_db)
) -> ProviderOut:
    existing = await db.execute(
        select(Provider).where(Provider.name == body.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"提供商已存在: {body.name}")
    slug = await _unique_slug(db, body.slug or "", fallback=body.name)
    obj = await cat.create_provider(
        db,
        name=body.name,
        slug=slug,
        base_url=body.base_url,
        api_key=body.api_key,
        enabled=body.enabled,
    )
    await db.commit()
    return _provider_to_out(await cat.get_provider(db, obj.id))


@providers_router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: str, body: ProviderUpdate, db: AsyncSession = Depends(get_db)
) -> ProviderOut:
    obj = await cat.get_provider(db, provider_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="provider not found")
    # api_key 传空字符串表示"不改";传掩码也视为"不改"(前端回填的是掩码,不能直接存)
    api_key = body.api_key if body.api_key and not _is_mask(body.api_key) else None
    # slug 传空 = 不改;传了值才规整 + 去重
    slug = None
    if body.slug is not None and body.slug.strip():
        slug = await _unique_slug(
            db, body.slug, fallback=obj.name, exclude_id=provider_id
        )
    updated = await cat.update_provider(
        db,
        provider_id,
        name=body.name,
        slug=slug,
        base_url=body.base_url,
        api_key=api_key,
        enabled=body.enabled,
    )
    await db.commit()
    return _provider_to_out(await cat.get_provider(db, provider_id))


@providers_router.delete("/{provider_id}")
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    ok = await cat.delete_provider(db, provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="provider not found")
    await db.commit()
    return {"ok": True}


@providers_router.post("/{provider_id}/discover", response_model=ModelDiscoveryResult)
async def discover_provider_models(
    provider_id: str, db: AsyncSession = Depends(get_db)
) -> ModelDiscoveryResult:
    """通过提供商的 OpenAI 兼容 /models 接口发现可用模型,并同步进 DB。"""
    obj = await cat.get_provider(db, provider_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="provider not found")

    try:
        found = await discover_models(
            obj.base_url,
            obj.api_key,
            verify_tls=get_settings().model_discovery_verify_tls,
        )
    except ModelDiscoveryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    before = {m.id for m in obj.models}
    ids = [m["id"] for m in found]
    names = {m["id"]: m["name"] for m in found}
    await cat.upsert_models(db, provider_id, ids, display_names=names)
    await db.commit()

    added = len([i for i in ids if i not in before])
    logger.info(
        "[models] provider=%s 发现 %d 个模型(新增 %d)", obj.name, len(ids), added
    )
    return ModelDiscoveryResult(provider_id=provider_id, models=ids, added=added)


# ---------- Model ----------


@models_router.get("", response_model=list[ModelOut])
async def list_models(db: AsyncSession = Depends(get_db)) -> list[ModelOut]:
    objs = await cat.list_models(db)
    return [ModelOut.model_validate(o) for o in objs]


@models_router.post("/{model_id}/default", response_model=list[ModelOut])
async def set_default_model(
    model_id: str, db: AsyncSession = Depends(get_db)
) -> list[ModelOut]:
    obj = await cat.get_model(db, model_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="model not found")
    await cat.set_default_model(db, model_id)
    await db.commit()
    return [ModelOut.model_validate(o) for o in await cat.list_models(db)]


@models_router.delete("/{model_id}/default", response_model=list[ModelOut])
async def unset_default_model(
    model_id: str, db: AsyncSession = Depends(get_db)
) -> list[ModelOut]:
    await cat.set_default_model(db, None)
    await db.commit()
    return [ModelOut.model_validate(o) for o in await cat.list_models(db)]
