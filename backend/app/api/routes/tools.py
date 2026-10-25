"""/api/tools 工具管理。

- GET    /api/tools                     列出全部工具(内置 + 上传的)
- POST   /api/tools                     新建工具(纯元数据,无代码)
- POST   /api/tools/upload              上传 zip 工具包(注册为可调用工具)
- GET    /api/tools/{id}                工具详情
- PATCH  /api/tools/{id}                更新工具(内置工具不允许编辑)
- DELETE /api/tools/{id}                删除工具(内置工具不允许删除)
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db import catalog_repository as cat
from app.schemas.catalog import ToolCreate, ToolOut, ToolUpdate
from app.tools_loader import (
    MAX_ZIP_BYTES,
    ToolLoadError,
    load_tool_package,
    unload_tool_package,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_out(obj) -> ToolOut:
    return ToolOut.model_validate(obj)


async def _replace_tool_package(
    db: AsyncSession,
    *,
    tool_id: str,
    zip_path: Path,
    display_name: str | None,
    description: str | None,
) -> list[ToolOut]:
    """用新的 zip 覆盖某个已有上传工具的实现。

    语义:
      - 工具**名字不变**(DB 里的 name / id 不动,agent 的工具绑定不受影响);
      - 代码换成新 zip 里的内容(旧解压目录删掉);
      - 显示名 / 描述默认沿用旧值,前端显式传了才覆盖;
      - 新 zip 里注册的工具名必须和原工具一致,否则视为「换了工具」→
        报错并回滚,避免绑定关系错位。

    内置工具(builtin=True)不允许替换 —— 它们的代码在仓库里。
    """
    obj = await cat.get_tool(db, tool_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="tool not found")
    if obj.builtin:
        raise HTTPException(status_code=400, detail="内置工具不允许替换实现")

    old_name = obj.name
    old_dir = obj.source_dir
    # 加载到**原来的 tool_id** 下:解压目录路径不变,agent 的绑定也不用动
    try:
        metas = load_tool_package(tool_id, zip_path, known_names={old_name})
    except ToolLoadError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    names = {m.name for m in metas}
    if names != {old_name}:
        # 名字对不上 → 这次上传其实是个新工具,不是替换
        unload_tool_package(tool_id, [m.name for m in metas])
        raise HTTPException(
            status_code=400,
            detail=(
                f"zip 里注册的工具是 {', '.join(sorted(names))},"
                f"与要替换的「{old_name}」不一致"
            ),
        )

    meta = metas[0]
    await cat.update_tool(
        db,
        tool_id,
        display_name=display_name if display_name is not None else obj.display_name,
        description=description if description is not None else obj.description,
    )
    # source_dir 变了(理论上还是同一个路径),刷新一下
    obj.source_dir = meta.source_dir
    await db.commit()
    await db.refresh(obj)

    # 旧解压目录跟新的不是同一个就清掉
    if old_dir and old_dir != meta.source_dir:
        shutil.rmtree(old_dir, ignore_errors=True)

    logger.info("[tools] 工具 %s 已用新 zip 替换实现", old_name)
    return [_to_out(obj)]


@router.get("", response_model=list[ToolOut])
async def list_tools(db: AsyncSession = Depends(get_db)) -> list[ToolOut]:
    objs = await cat.list_tools(db)
    return [_to_out(o) for o in objs]


@router.post("", response_model=ToolOut)
async def create_tool(
    body: ToolCreate, db: AsyncSession = Depends(get_db)
) -> ToolOut:
    existing = await cat.get_tool_by_name(db, body.name)
    if existing is not None:
        raise HTTPException(status_code=400, detail=f"工具名已存在: {body.name}")
    obj = await cat.create_tool(
        db,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        builtin=False,
    )
    await db.commit()
    await db.refresh(obj)
    return _to_out(obj)


@router.post("/upload", response_model=list[ToolOut])
async def upload_tool(
    file: UploadFile = File(...),
    replace_tool_id: str | None = Form(None),
    display_name: str | None = Form(None),
    description: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> list[ToolOut]:
    """上传 zip 工具包 → 解压 → import → 注册工具 → 写 DB。

    zip 里应含 .py 模块,模块里调用 ``register_tool(name, tool)``。
    可选 manifest.json 提供显示名 / 描述。

    replace_tool_id:非空时表示「替换某个已有工具的实现」——
      用于「编辑工具」弹窗里重新上传 zip 覆盖代码,此时该工具的
      显示名 / 描述保留(除非显式传 display_name / description)。
    """
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="只支持上传 zip 包")

    # 落临时文件(限制大小)
    tmp_dir = Path(tempfile.mkdtemp(prefix="swift-agent-tool-"))
    zip_path = tmp_dir / "package.zip"
    total = 0
    try:
        with zip_path.open("wb") as f:
            while chunk := await file.read(64 * 1024):
                total += len(chunk)
                if total > MAX_ZIP_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"zip 超过 {MAX_ZIP_BYTES // 1024 // 1024}MB 上限",
                    )
                f.write(chunk)
        await file.close()

        # ── 替换模式:覆盖某个已有工具的实现 ──
        # 「编辑工具」弹窗里重新上传 zip:工具名不变,只换代码,
        # 显示名 / 描述默认保留(除非前端显式传了新的)。
        if replace_tool_id:
            return await _replace_tool_package(
                db,
                tool_id=replace_tool_id,
                zip_path=zip_path,
                display_name=display_name,
                description=description,
            )

        # 用临时 id 试加载;成功后再落 DB
        tool_id = uuid.uuid4().hex
        try:
            metas = load_tool_package(tool_id, zip_path)
        except ToolLoadError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        created: list[ToolOut] = []
        try:
            for meta in metas:
                dup = await cat.get_tool_by_name(db, meta.name)
                if dup is not None:
                    raise HTTPException(
                        status_code=400, detail=f"工具名已存在: {meta.name}"
                    )
                obj = await cat.create_tool(
                    db,
                    name=meta.name,
                    display_name=display_name or meta.display_name,
                    description=(
                        description if description is not None else meta.description
                    ),
                    builtin=False,
                    source_dir=meta.source_dir,
                )
                created.append(obj)
            await db.commit()
        except HTTPException:
            # DB 写失败 → 回滚注册 + 删目录,避免留下半截状态
            await db.rollback()
            unload_tool_package(tool_id, [m.name for m in metas])
            raise

        logger.info("[tools] 上传工具包成功:%s", [m.name for m in metas])
        return [_to_out(o) for o in created]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: str, db: AsyncSession = Depends(get_db)) -> ToolOut:
    obj = await cat.get_tool(db, tool_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="tool not found")
    return _to_out(obj)


@router.patch("/{tool_id}", response_model=ToolOut)
async def update_tool(
    tool_id: str, body: ToolUpdate, db: AsyncSession = Depends(get_db)
) -> ToolOut:
    obj = await cat.get_tool(db, tool_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="tool not found")
    if obj.builtin:
        raise HTTPException(status_code=400, detail="内置工具不允许编辑")

    updated = await cat.update_tool(
        db,
        tool_id,
        display_name=body.display_name,
        description=body.description,
        name=body.name,
    )
    await db.commit()
    await db.refresh(updated)
    return _to_out(updated)


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    obj = await cat.get_tool(db, tool_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="tool not found")
    if obj.builtin:
        raise HTTPException(status_code=400, detail="内置工具不允许删除")

    # 卸载运行时注册 + 删解压目录
    if obj.source_dir:
        unload_tool_package(tool_id, [obj.name])
    await cat.delete_tool(db, tool_id)
    await db.commit()
    return {"ok": True}
