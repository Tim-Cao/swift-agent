"""/api/health 健康检查(无依赖,保持简洁)。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health() -> dict:
    return {"status": "ok"}
