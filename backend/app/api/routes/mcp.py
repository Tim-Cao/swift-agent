"""/api/mcp:MCP 服务端管理。

MCP server 的元数据存在 ``mcp_servers`` 表里(v11.3,从 .mcp.json 挪过来)。

- GET    /api/mcp                 列出 MCP server
- POST   /api/mcp                 新增
- PATCH  /api/mcp/{id}            修改
- DELETE /api/mcp/{id}            删除
- POST   /api/mcp/{id}/test       测试连接(连一下看能不能拿到工具)
- POST   /api/mcp/reload          重新装载全部启用的 server
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db import catalog_repository as cat
from app.schemas.catalog import (
    MCPServerCreate,
    MCPServerOut,
    MCPServerUpdate,
)
from app.services import mcp_config as mc

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_out(obj) -> MCPServerOut:
    return MCPServerOut(
        id=obj.id,
        name=obj.name,
        transport=obj.transport,
        transport_label=mc.transport_label(obj.transport),
        config=mc.parse_config(obj.config_json),
        description=mc.describe(obj),
        tool_names=_parse_tool_names(obj.tool_names),
        status=obj.status,
        status_detail=obj.status_detail,
        enabled=obj.enabled,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


def _parse_tool_names(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(t) for t in data] if isinstance(data, list) else []


def _check_transport(transport: str) -> None:
    if transport not in mc.TRANSPORTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的传输方式: {transport}(可选: {', '.join(mc.TRANSPORTS)})",
        )


def _describe_error(exc: BaseException) -> str:
    """把异常压成一句人话。

    MCP 客户端用 TaskGroup 包着连接,失败时抛的是 ExceptionGroup,
    ``str(e)`` 只有 "unhandled errors in a TaskGroup (1 sub-exception)" 这种
    没有任何信息量的话,真正的错因(比如子进程启动就报
    "MINIMAX_API_KEY environment variable is required")被埋在
    ``exceptions`` 里。这里一路剥到最深处的那个异常再取它的信息。
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        # ExceptionGroup / TaskGroup:剥到子异常
        subs = getattr(cur, "exceptions", None)
        if isinstance(subs, (list, tuple)) and subs:
            cur = subs[0]
            continue
        break
    text = str(cur).strip() if cur is not None else ""
    return (text or str(exc))[:500]


@router.get("", response_model=list[MCPServerOut])
async def list_mcp(db: AsyncSession = Depends(get_db)) -> list[MCPServerOut]:
    objs = await cat.list_mcp_servers(db)
    return [_to_out(o) for o in objs]


@router.post("", response_model=MCPServerOut)
async def create_mcp(
    body: MCPServerCreate, db: AsyncSession = Depends(get_db)
) -> MCPServerOut:
    _check_transport(body.transport)
    existing = await cat.get_mcp_server_by_name(db, body.name)
    if existing is not None:
        raise HTTPException(status_code=400, detail=f"MCP 已存在: {body.name}")
    obj = await cat.create_mcp_server(
        db,
        name=body.name,
        transport=body.transport,
        config_json=mc.dump_config(body.config),
        enabled=body.enabled,
    )
    await db.commit()
    return _to_out(await cat.get_mcp_server(db, obj.id))


@router.patch("/{server_id}", response_model=MCPServerOut)
async def update_mcp(
    server_id: str, body: MCPServerUpdate, db: AsyncSession = Depends(get_db)
) -> MCPServerOut:
    obj = await cat.get_mcp_server(db, server_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if body.transport is not None:
        _check_transport(body.transport)
    if body.name and body.name != obj.name:
        clash = await cat.get_mcp_server_by_name(db, body.name)
        if clash is not None:
            raise HTTPException(status_code=400, detail=f"MCP 已存在: {body.name}")
    await cat.update_mcp_server(
        db,
        server_id,
        name=body.name,
        transport=body.transport,
        config_json=mc.dump_config(body.config) if body.config is not None else None,
        enabled=body.enabled,
    )
    await db.commit()
    return _to_out(await cat.get_mcp_server(db, server_id))


@router.delete("/{server_id}")
async def delete_mcp(server_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    ok = await cat.delete_mcp_server(db, server_id)
    if not ok:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await db.commit()
    return {"ok": True}


@router.post("/{server_id}/test")
async def test_mcp(server_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """测试连接:真去连一下,看能不能拿到工具。"""
    obj = await cat.get_mcp_server(db, server_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="MCP server not found")

    from langchain_mcp_adapters.client import MultiServerMCPClient

    # 必须注入密钥:stdio 子进程要靠 MINIMAX_API_KEY 才能起来
    # (和启动装载路径 app/core/mcp.py 走同一个 inject_secrets)
    cfg = mc.inject_secrets(mc.to_client_config(obj))
    try:
        client = MultiServerMCPClient({obj.name: cfg})
        tools = await client.get_tools()
        names = sorted(t.name for t in tools)
        await cat.update_mcp_server(
            db,
            server_id,
            tool_names=json.dumps(names, ensure_ascii=False),
            status="connected",
            status_detail=f"{len(names)} 个工具",
        )
        await db.commit()
        return {"ok": True, "tools": names}
    except Exception as e:  # noqa: BLE001
        detail = _describe_error(e)
        logger.warning("[mcp] 测试 %s 失败: %s", obj.name, detail)
        await cat.update_mcp_server(
            db,
            server_id,
            status="failed",
            status_detail=detail,
        )
        await db.commit()
        return {"ok": False, "error": detail}


@router.post("/reload")
async def reload_mcp(db: AsyncSession = Depends(get_db)) -> dict:
    """重新装载全部启用的 MCP server(改了配置之后用)。"""
    from app.core.mcp import init_mcp, shutdown_mcp

    try:
        await shutdown_mcp()
    except Exception as e:  # noqa: BLE001
        logger.debug("[mcp] shutdown 失败(忽略): %s", e)
    try:
        tools = await init_mcp()
        return {"ok": True, "tools": sorted(t.name for t in tools)}
    except Exception as e:  # noqa: BLE001
        logger.warning("[mcp] 重新装载失败: %s", e)
        return {"ok": False, "error": str(e)[:500]}
