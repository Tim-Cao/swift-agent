"""/api/downloads/<session_id>/<filename>:静态文件下载(防路径穿越)。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

UPLOAD_ROOT = Path("/tmp/swift-agent")


@router.get("/{session_id}/{filename}")
async def download(session_id: str, filename: str):
    """返回 /tmp/swift-agent/<session_id>/<filename>。防 zip slip。"""
    safe_name = Path(filename).name  # 去掉任何路径成分
    if safe_name != filename or not safe_name:
        raise HTTPException(status_code=400, detail="invalid filename")
    # session_id 也要校验(只能 32 位 hex,与模型 uuid.uuid4().hex 一致)
    if not all(c in "0123456789abcdef" for c in session_id) or len(session_id) != 32:
        raise HTTPException(status_code=400, detail="invalid session_id")
    file_path = (UPLOAD_ROOT / session_id / safe_name).resolve()
    if not str(file_path).startswith(str(UPLOAD_ROOT.resolve())):
        raise HTTPException(status_code=403, detail="forbidden")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    # mime 推断
    mime = "application/octet-stream"
    if safe_name.lower().endswith(".xlsx"):
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif safe_name.lower().endswith(".csv"):
        mime = "text/csv"

    return FileResponse(
        file_path,
        filename=safe_name,
        media_type=mime,
    )