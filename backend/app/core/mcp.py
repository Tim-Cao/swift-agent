"""MCP 客户端单例 + 工具装载。

v11.3:MCP server 的元数据从 ``.mcp.json`` 挪到了数据库(``mcp_servers`` 表),
在「MCP 管理」页里增删改。这里从 DB 读配置来建 client。

  - 启动期(lifespan)调 `await init_mcp()`,通过 langchain-mcp-adapters 的
    MultiServerMCPClient 连上启用的 server,缓存工具列表。
  - 工具始终加载到 supervisor(由 builder.py 调 get_mcp_tools()),
    由 WebSearchGateMiddleware 根据每轮请求的 web_search_enabled 决定是否
    在 LLM 看到工具列表前剔除。
  - 密钥不入库:config 里的 env 值写成 ``${ENV_NAME}`` 引用,连接时从环境变量
    取值;另外沿用历史的自动注入:
      LLM_API_KEY   → MINIMAX_API_KEY (minimax 平台同一个 key,已存在 .env)
      MINIMAX_API_HOST → MINIMAX_API_HOST (可选,默认 https://api.minimaxi.com)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

# .env 的加载已经挪到 app.services.mcp_config(import 它就会 load 一次),
# 密钥注入统一走那里的 inject_secrets。
from app.services.mcp_config import inject_secrets

logger = logging.getLogger(__name__)


# 默认 MCP 配置文件路径:backend/.mcp.json(只作为 DB 播种的来源 / 兜底)
_DEFAULT_MCP_CONFIG = Path(__file__).resolve().parents[2] / ".mcp.json"

_client: MultiServerMCPClient | None = None
_tools: list[BaseTool] | None = None
_tool_names: frozenset[str] = frozenset()


def _load_config(path: Path) -> dict:
    """读 .mcp.json,只支持顶层 mcpServers 字段。"""
    if not path.exists():
        raise FileNotFoundError(f"MCP config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    servers = data.get("mcpServers") or {}
    if not servers:
        raise ValueError(f"No mcpServers defined in {path}")
    return servers


async def _load_db_connections() -> tuple[dict[str, dict], list[tuple[str, str, str]]]:
    """从 mcp_servers 表读出启用的 server。

    返回 ``(connections, records)``:
      - connections: server 名 → MultiServerMCPClient 认的配置
      - records:    (id, name, transport) 列表,用来回写连接状态
    """
    from app.db import catalog_repository as cat
    from app.db.base import get_session_factory
    from app.services.mcp_config import inject_secrets, to_client_config

    factory = get_session_factory()
    async with factory() as db:
        objs = await cat.list_mcp_servers(db)
        connections: dict[str, dict] = {}
        records: list[tuple[str, str, str]] = []
        for obj in objs:
            if not obj.enabled:
                continue
            connections[obj.name] = inject_secrets(to_client_config(obj))
            records.append((obj.id, obj.name, obj.transport))
    return connections, records


async def _save_status(
    records: list[tuple[str, str, str]],
    results: dict[str, tuple[str, list[str], str]],
) -> None:
    """把每个 server 的连接结果写回 DB(status / tool_names)。"""
    from app.db import catalog_repository as cat
    from app.db.base import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        for server_id, name, _transport in records:
            status, tools, detail = results.get(
                name, ("unknown", [], "未尝试连接")
            )
            await cat.update_mcp_server(
                db,
                server_id,
                status=status,
                status_detail=detail,
                tool_names=json.dumps(tools, ensure_ascii=False),
            )
        await db.commit()


async def init_mcp(config_path: Path | str | None = None) -> list[BaseTool]:
    """启动时调用:连接 MCP server、装载工具、缓存工具名集合。

    重复调用是幂等的(单例);先 shutdown_mcp() 再调可以重新装载。

    配置来源优先级:
      1. DB 的 mcp_servers 表(「MCP 管理」页维护的)
      2. 表里一条都没有时兜底读 .mcp.json(DB 播种失败时的保险)
    """
    global _client, _tools, _tool_names
    if _tools is not None:
        return _tools

    connections, records = await _load_db_connections()

    if not connections:
        # DB 里没有启用的 server —— 兜底读文件(老部署 / 播种失败)
        path = Path(config_path) if config_path else _DEFAULT_MCP_CONFIG
        try:
            servers = _load_config(path)
        except Exception as e:  # noqa: BLE001
            logger.info("没有可用的 MCP 配置: %s", e)
            _tools = []
            _tool_names = frozenset()
            return _tools
        connections = {name: inject_secrets(cfg) for name, cfg in servers.items()}
        logger.info("MCP 配置来自文件 %s", path)

    logger.info("Initializing MCP client with servers: %s", list(connections))
    _client = MultiServerMCPClient(connections)

    # 逐个 server 装载 —— 一个连不上不影响其它
    all_tools: list[BaseTool] = []
    results: dict[str, tuple[str, list[str], str]] = {}
    for name in connections:
        try:
            tools = await _client.get_tools(server_name=name)
        except Exception as e:  # noqa: BLE001
            detail = str(e)[:300]
            logger.warning("[mcp] server %s 装载失败: %s", name, detail)
            results[name] = ("failed", [], detail)
            continue
        names = sorted(t.name for t in tools if getattr(t, "name", None))
        all_tools.extend(tools)
        results[name] = ("connected", names, f"{len(names)} 个工具")

    _tools = all_tools
    _tool_names = frozenset(_tool_name(t) for t in _tools if _tool_name(t))
    logger.info(
        "MCP loaded %d tool(s) from %d server(s): %s",
        len(_tools),
        len(connections),
        sorted(_tool_names),
    )

    if records:
        try:
            await _save_status(records, results)
        except Exception as e:  # noqa: BLE001
            logger.debug("[mcp] 回写状态失败(忽略): %s", e)

    return _tools


def get_mcp_tools() -> list[BaseTool]:
    """获取已加载的 MCP 工具列表(供 builder.py 追加到 supervisor)。"""
    if _tools is None:
        raise RuntimeError(
            "MCP not initialized. Call init_mcp() in lifespan first."
        )
    return list(_tools)


def get_mcp_tool_names() -> frozenset[str]:
    """获取 MCP 工具名集合(供 WebSearchGateMiddleware 过滤用)。"""
    if _tool_names is None:
        raise RuntimeError(
            "MCP not initialized. Call init_mcp() in lifespan first."
        )
    return _tool_names


async def shutdown_mcp() -> None:
    """关闭 MCP 客户端(lifespan 退出时 / 重新装载前调用)。"""
    global _client, _tools, _tool_names
    if _client is not None:
        # MultiServerMCPClient 通过 __aexit__ 关闭连接
        try:
            await _client.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            logger.debug("MCP client shutdown raised (ignored)")
    _client = None
    _tools = None
    _tool_names = frozenset()


def _tool_name(tool: BaseTool | dict) -> str | None:
    """提取工具名(BaseTool 或 dict 形态都支持)。"""
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None
