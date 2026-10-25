"""MCP 配置:DB 记录 ⇄ langchain-mcp-adapters 配置。

v11.3:MCP server 的元数据从 ``.mcp.json`` 文件挪到数据库。
这个模块负责两种翻译:
  - ``to_client_config``  DB 记录 → MultiServerMCPClient 认的 dict
  - ``from_client_config``  .mcp.json 形态 → DB 记录(播种用)

传输方式:
  - ``stdio``            本地子进程:{command, args, env}
  - ``streamable_http`` HTTP 端点:{url, headers}

密钥处理:跟 provider 的 api_key 一样 —— **不存明文**。
config 里的 env 值写成 ``${ENV_NAME}`` 引用,真正连接时从环境变量取值。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.db.models import MCPServer

logger = logging.getLogger(__name__)

# 把 backend/.env 载入 os.environ,让 LLM_API_KEY / MINIMAX_API_HOST 这类
# secret 在**任何**用到 inject_secrets 的地方都可用。
#
# 之前这一步只在 app/core/mcp.py 里做(import 那个模块才有副作用),于是
# 「MCP 管理 → 测试连接」那条路径(只 import mcp_config)拿不到 LLM_API_KEY,
# 子进程启动即报 MINIMAX_API_KEY environment variable is required。
# 放在这里,谁 import 谁生效,不再依赖 import 顺序。
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)

# 两种支持的传输方式
TRANSPORT_STDIO = "stdio"
TRANSPORT_STREAMABLE_HTTP = "streamable_http"
TRANSPORTS = (TRANSPORT_STDIO, TRANSPORT_STREAMABLE_HTTP)

# 传输方式 → 前端显示的中文名
TRANSPORT_LABELS = {
    TRANSPORT_STDIO: "stdio",
    TRANSPORT_STREAMABLE_HTTP: "Streamable HTTP",
}

# ``${ENV_NAME}`` 引用
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def transport_label(transport: str) -> str:
    """传输方式的中文显示名(未知值原样返回)。"""
    return TRANSPORT_LABELS.get(transport, transport)


def parse_config(config_json: str | None) -> dict[str, Any]:
    """把 config_json 解析成 dict(解析失败返回空 dict,不抛)。"""
    if not config_json:
        return {}
    try:
        data = json.loads(config_json)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def dump_config(config: dict[str, Any]) -> str:
    """把 config dict 序列化成 JSON 字符串。"""
    return json.dumps(config, ensure_ascii=False)


def _resolve_env(value: Any) -> Any:
    """把 ``${ENV_NAME}`` 换成环境变量里的值。

    - 整个字符串就是一个引用 → 换成 env 的值(没有就留空)
    - 字符串里嵌着引用 → 逐个替换
    - 非字符串 → 原样返回
    """
    if not isinstance(value, str):
        return value
    if value.startswith("${") and value.endswith("}") and _ENV_REF.fullmatch(value):
        return os.environ.get(_ENV_REF.fullmatch(value).group(1), "")
    return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)


def to_client_config(obj: MCPServer) -> dict[str, Any]:
    """DB 记录 → MultiServerMCPClient 的 server 配置。

    输出形如::

        {"transport": "stdio", "command": "uvx", "args": [...], "env": {...}}
        {"transport": "streamable_http", "url": "https://...", "headers": {...}}

    注意:这里**不注入**平台密钥(见 inject_secrets)。调用方拿到配置后要再走
    一次 inject_secrets,才能真正连上 minimax 这类需要密钥的 server。
    """
    cfg = parse_config(obj.config_json)

    if obj.transport == TRANSPORT_STREAMABLE_HTTP:
        url = str(cfg.get("url") or "").strip()
        out: dict[str, Any] = {"transport": "streamable_http", "url": url}
        headers = cfg.get("headers")
        if isinstance(headers, dict) and headers:
            out["headers"] = {k: _resolve_env(v) for k, v in headers.items()}
        return out

    # stdio
    command = str(cfg.get("command") or "").strip()
    out = {"transport": "stdio", "command": command}
    args = cfg.get("args")
    if isinstance(args, list):
        out["args"] = [str(a) for a in args]
    env = cfg.get("env")
    if isinstance(env, dict) and env:
        out["env"] = {k: _resolve_env(v) for k, v in env.items()}
    return out


def inject_secrets(server_cfg: dict[str, Any]) -> dict[str, Any]:
    """注入 minimax 平台密钥,不修改原 dict。

    - `LLM_API_KEY`(已存在 .env)→ `MINIMAX_API_KEY`
    - `MINIMAX_API_HOST`(可选,默认 minimaxi.com)→ `MINIMAX_API_HOST`

    启动装载和「测试连接」两条路径都必须过这一步,否则 stdio 子进程拿不到
    密钥,minimax-coding-plan-mcp 启动即报
    ``MINIMAX_API_KEY environment variable is required``。
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


def from_client_config(name: str, cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """.mcp.json 形态的一条 server → (transport, config)。

    播种用:把项目里已有的 ``.mcp.json`` 转成 DB 记录。
    """
    transport = str(cfg.get("transport") or TRANSPORT_STDIO)
    if transport not in TRANSPORTS:
        transport = TRANSPORT_STDIO
    config: dict[str, Any] = {}
    if transport == TRANSPORT_STREAMABLE_HTTP:
        if cfg.get("url"):
            config["url"] = cfg["url"]
        if isinstance(cfg.get("headers"), dict) and cfg["headers"]:
            config["headers"] = cfg["headers"]
    else:
        if cfg.get("command"):
            config["command"] = cfg["command"]
        if isinstance(cfg.get("args"), list):
            config["args"] = cfg["args"]
        if isinstance(cfg.get("env"), dict) and cfg["env"]:
            config["env"] = cfg["env"]
    return transport, config


def describe(obj: MCPServer) -> str:
    """一行话描述这个 server 的连接方式(给卡片用)。"""
    cfg = parse_config(obj.config_json)
    if obj.transport == TRANSPORT_STREAMABLE_HTTP:
        return str(cfg.get("url") or "(未设置 URL)")
    cmd = cfg.get("command") or "(未设置命令)"
    args = cfg.get("args") or []
    if args:
        return f"{cmd} {' '.join(str(a) for a in args)}"
    return str(cmd)


__all__ = [
    "TRANSPORTS",
    "TRANSPORT_STDIO",
    "TRANSPORT_STREAMABLE_HTTP",
    "transport_label",
    "parse_config",
    "dump_config",
    "to_client_config",
    "inject_secrets",
    "from_client_config",
    "describe",
]
