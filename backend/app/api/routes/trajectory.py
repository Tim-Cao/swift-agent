"""/api/sessions/{id}/trajectory + /api/sessions/{id}/log/export

提供会话的"轨迹视图"和"原始日志下载"。

- GET /api/sessions/{session_id}/trajectory
  返回折叠好的 ``Trajectory``(header + turns + steps + summary),
  用于前端 ``TrajectoryDrawer`` 渲染。

- GET /api/sessions/{session_id}/log/export
  返回原始 ``session.jsonl`` 字节流,文件名 ``session-<id>.jsonl``。
  供调试 / 回放 / 离线分析使用。

设计参考 deepseek-harness 的 ``/api/session.export``(返回 ZIP),
我们这里只返回单文件 JSONL,不打包(无 subagent 子会话)。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.db import repository as repo
from app.trajectory import SessionLogReader, Trajectory

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{session_id}/trajectory", response_model=Trajectory)
async def get_trajectory(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Trajectory:
    """返回会话的折叠轨迹。

    - 会话不存在 → 404
    - 会话存在但无 JSONL → 返回 ``summary.empty=true`` 的占位 Trajectory
    """
    obj = await repo.get_session(db, session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="session not found")

    settings = get_settings()
    reader = SessionLogReader(
        session_id=session_id,
        root=settings.trajectory_log_dir,
    )
    return await reader.read()


@router.get("/{session_id}/log/export")
async def export_session_log(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """下载会话的原始 JSONL 日志。

    响应:
      - Content-Type: application/x-ndjson
      - Content-Disposition: attachment; filename="session-<id>.jsonl"
      - Body: 原始 JSONL 字节

    会话不存在 → 404;日志文件不存在 → 200 但 body 为空(保留向前端返回
    一致的"会话存在但暂无日志"的语义)。
    """
    obj = await repo.get_session(db, session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="session not found")

    settings = get_settings()
    reader = SessionLogReader(
        session_id=session_id,
        root=settings.trajectory_log_dir,
    )
    raw = await reader.read_raw_bytes()
    return Response(
        content=raw,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="session-{session_id}.jsonl"',
            "X-Session-Id": session_id,
        },
    )