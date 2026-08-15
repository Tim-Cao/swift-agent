"""MCP 客户端单例 + 工具装载。

设计:
  - 启动期(lifespan)调 `await init_mcp()`,通过 langchain-mcp-adapters 的
    MultiServerMCPClient 连上 `minimax_coding_plan` stdio server,缓存工具列表。
  - 工具始终加载到 supervisor(由 builder.py 调 get_mcp_tools()),
    由 WebSearchGateMiddleware 根据每轮请求的 web_search_enabled 决定是否
    在 LLM 看到工具列表前剔除。
  - API key 不入 `.mcp.json`(避免入库),启动时从 env 读取注入:
      LLM_API_KEY   → MINIMAX_API_KEY (minimax 平台同一个 key,已存在 .env)
      MINIMAX_API_HOST → MINIMAX_API_HOST (可选,默认 https://api.minimaxi.com)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# 加载项目根 .env(backend/.env)到 os.environ,使 LLM_API_KEY / MINIMAX_API_HOST
# 等 secret 在 MCP 子进程启动前可用。pydantic_settings 只在构造 Settings 实例
# 时按需读 env,不会污染全局 os.environ,这里显式 load 一次。
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)

# 默认 MCP 配置文件路径:backend/.mcp.json
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


def _inject_secrets(server_cfg: dict) -> dict:
    """从环境变量注入密钥,不修改原 dict。

    - `LLM_API_KEY`(已存在 .env)→ MINIMAX_API_KEY
    - `MINIMAX_API_HOST`(可选,默认 minimaxi.com)→ MINIMAX_API_HOST
    """
    cfg = dict(server_cfg)
    env = dict(cfg.get("env") or {})

    api_key = env.get("MINIMAX_API_KEY") or os.environ.get("LLM_API_KEY", "")
    if api_key and "MINIMAX_API_KEY" not in env:
        env["MINIMAX_API_KEY"] = api_key

    if "MINIMAX_API_HOST" not in env:
        env["MINIMAX_API_HOST"] = os.environ.get(
            "MINIMAX_API_HOST", "https://api.minimaxi.com"
        )

    cfg["env"] = env
    return cfg


async def init_mcp(config_path: Path | str | None = None) -> list[BaseTool]:
    """启动时调用:连接 MCP server、装载工具、缓存工具名集合。

    重复调用是幂等的(单例)。
    """
    global _client, _tools, _tool_names
    if _tools is not None:
        return _tools

    path = Path(config_path) if config_path else _DEFAULT_MCP_CONFIG
    servers = _load_config(path)

    # 注入密钥后构造 client
    servers_with_secrets = {name: _inject_secrets(cfg) for name, cfg in servers.items()}
    logger.info("Initializing MCP client with servers: %s", list(servers_with_secrets))
    _client = MultiServerMCPClient(servers_with_secrets)

    _tools = await _client.get_tools()
    _tool_names = frozenset(_tool_name(t) for t in _tools if _tool_name(t))
    logger.info(
        "MCP loaded %d tool(s): %s",
        len(_tools),
        sorted(_tool_names),
    )
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
    """关闭 MCP 客户端(lifespan 退出时调用)。"""
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