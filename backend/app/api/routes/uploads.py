"""/api/uploads:接收 zip,解压到 /tmp/swift-agent/<session_id>/,返回 CSV 目录。"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.chat_service import ensure_session

logger = logging.getLogger(__name__)
router = APIRouter()

# 上传 / 工作目录根
UPLOAD_ROOT = Path("/tmp/swift-agent")
MAX_ZIP_BYTES = 100 * 1024 * 1024  # 100MB


@router.post("")
async def upload_zip(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """接收 zip → 解压到 /tmp/swift-agent/<sid>/csv/,返回目录路径。"""
    # 1. session 处理
    if session_id:
        sid = session_id
    else:
        sid, _ = await ensure_session(db, None, None)
        await db.commit()

    # 2. session 目录
    session_dir = UPLOAD_ROOT / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = session_dir / "csv"

    # 3. 落 zip
    zip_name = f"{uuid.uuid4().hex}.zip"
    zip_path = session_dir / zip_name
    total = 0
    try:
        with zip_path.open("wb") as f:
            while chunk := await file.read(64 * 1024):
                total += len(chunk)
                if total > MAX_ZIP_BYTES:
                    raise HTTPException(status_code=413, detail=f"zip > {MAX_ZIP_BYTES // 1024 // 1024}MB")
                f.write(chunk)
    finally:
        await file.close()

    # 4. 解压
    if csv_dir.exists():
        shutil.rmtree(csv_dir)
    csv_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    skipped: list[str] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                target = (csv_dir / member.filename).resolve()
                if not str(target).startswith(str(csv_dir.resolve())):
                    skipped.append(member.filename)
                    continue
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if member.filename.lower().endswith(".csv"):
                    extracted.append(member.filename)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="invalid zip file")

    logger.info(
        "uploaded zip sid=%s files=%d skipped=%d size=%d",
        sid, len(extracted), len(skipped), total,
    )

    return {
        "session_id": sid,
        "upload_dir": str(csv_dir.resolve()),
        "csv_files": sorted(extracted),
        "zip_path": str(zip_path.resolve()),
        "size_bytes": total,
        "skipped_unsafe": skipped,
    }