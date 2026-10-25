"""MCP 服务端管理:v11.3 把 MCP 元数据从 .mcp.json 挪进数据库。

覆盖:
- 列表 / 新增 / 编辑 / 删除
- 传输方式校验(只允许 stdio / streamable_http)
- 名称唯一
- config 的读写往返(command/args/env 与 url/headers)
- ${ENV_NAME} 引用在连接时才解析(库里不存明文)
- 描述文本(卡片上显示的那行)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from app.db.base import init_db
    from app.main import app

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _clear(client: AsyncClient) -> None:
    for s in (await client.get("/api/mcp")).json():
        await client.delete(f"/api/mcp/{s['id']}")


# --------------------------------------------------------------------------- #
# 1) CRUD
# --------------------------------------------------------------------------- #


async def test_list_empty_then_create(client: AsyncClient):
    await _clear(client)
    resp = await client.get("/api/mcp")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.post(
        "/api/mcp",
        json={
            "name": "minimax-coding-plan-mcp",
            "transport": "stdio",
            "config": {
                "command": "uvx",
                "args": ["--from", "minimax-coding-plan-mcp"],
            },
        },
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["name"] == "minimax-coding-plan-mcp"
    assert out["transport"] == "stdio"
    assert out["transport_label"] == "stdio"
    assert out["config"]["command"] == "uvx"
    assert out["config"]["args"] == ["--from", "minimax-coding-plan-mcp"]
    assert out["enabled"] is True
    assert out["status"] == "unknown"

    await _clear(client)


async def test_streamable_http_transport(client: AsyncClient):
    await _clear(client)
    resp = await client.post(
        "/api/mcp",
        json={
            "name": "remote-mcp",
            "transport": "streamable_http",
            "config": {"url": "https://example.com/mcp"},
        },
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["transport_label"] == "Streamable HTTP"
    assert out["description"] == "https://example.com/mcp"

    await _clear(client)


async def test_invalid_transport_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/mcp",
        json={"name": "bad", "transport": "sse", "config": {}},
    )
    assert resp.status_code == 400
    assert "sse" in resp.json()["detail"]


async def test_duplicate_name_rejected(client: AsyncClient):
    await _clear(client)
    payload = {"name": "dup-mcp", "transport": "stdio", "config": {"command": "x"}}
    assert (await client.post("/api/mcp", json=payload)).status_code == 200
    resp = await client.post("/api/mcp", json=payload)
    assert resp.status_code == 400
    assert "已存在" in resp.json()["detail"]
    await _clear(client)


async def test_update_and_delete(client: AsyncClient):
    await _clear(client)
    created = (
        await client.post(
            "/api/mcp",
            json={"name": "up-mcp", "transport": "stdio", "config": {"command": "a"}},
        )
    ).json()
    sid = created["id"]

    resp = await client.patch(
        f"/api/mcp/{sid}",
        json={"name": "up-mcp-2", "enabled": False, "config": {"command": "b"}},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["name"] == "up-mcp-2"
    assert out["enabled"] is False
    assert out["config"]["command"] == "b"

    resp = await client.delete(f"/api/mcp/{sid}")
    assert resp.status_code == 200
    assert (await client.get("/api/mcp")).json() == []

    assert (await client.delete(f"/api/mcp/{sid}")).status_code == 404


async def test_update_missing_returns_404(client: AsyncClient):
    assert (await client.patch("/api/mcp/nope", json={"name": "x"})).status_code == 404


# --------------------------------------------------------------------------- #
# 2) config 翻译层
# --------------------------------------------------------------------------- #


def test_to_client_config_stdio(monkeypatch):
    from app.db.models import MCPServer
    from app.services.mcp_config import to_client_config

    obj = MCPServer(
        name="s",
        transport="stdio",
        config_json=json.dumps(
            {"command": "uvx", "args": ["a"], "env": {"K": "${SOME_KEY}"}}
        ),
    )
    monkeypatch.setenv("SOME_KEY", "secret")
    cfg = to_client_config(obj)
    assert cfg == {
        "transport": "stdio",
        "command": "uvx",
        "args": ["a"],
        "env": {"K": "secret"},
    }


def test_to_client_config_http(monkeypatch):
    from app.db.models import MCPServer
    from app.services.mcp_config import to_client_config

    obj = MCPServer(
        name="h",
        transport="streamable_http",
        config_json=json.dumps(
            {"url": "https://x/mcp", "headers": {"Auth": "${TOK}"}}
        ),
    )
    monkeypatch.setenv("TOK", "abc")
    cfg = to_client_config(obj)
    assert cfg["transport"] == "streamable_http"
    assert cfg["url"] == "https://x/mcp"
    assert cfg["headers"] == {"Auth": "abc"}


def test_env_ref_keeps_plaintext_out_of_db():
    """库里存的应该是 ${VAR} 引用,不是明文密钥。"""
    from app.services.mcp_config import parse_config

    stored = json.dumps({"command": "x", "env": {"TOKEN": "${MY_TOKEN}"}})
    cfg = parse_config(stored)
    assert cfg["env"]["TOKEN"] == "${MY_TOKEN}"
    assert "secret" not in stored


def test_describe():
    from app.db.models import MCPServer
    from app.services.mcp_config import describe

    obj = MCPServer(
        name="s",
        transport="stdio",
        config_json=json.dumps({"command": "uvx", "args": ["--from", "pkg"]}),
    )
    assert describe(obj) == "uvx --from pkg"


def test_from_client_config():
    from app.services.mcp_config import from_client_config

    transport, config = from_client_config(
        "x", {"transport": "stdio", "command": "uvx", "args": ["a"], "env": {}}
    )
    assert transport == "stdio"
    assert config["command"] == "uvx"
    assert config["args"] == ["a"]
    # 空的 env 不该被存进去
    assert "env" not in config


# --------------------------------------------------------------------------- #
# 7) 密钥注入:测试连接和启动装载必须走同一条路
# --------------------------------------------------------------------------- #


def test_inject_secrets_adds_minimax_key(monkeypatch):
    """inject_secrets 把 LLM_API_KEY 注入成 MINIMAX_API_KEY。

    回归:之前 inject 只在 app/core/mcp.py 里做,而「测试连接」那条路径
    只 import mcp_config,子进程拿不到 MINIMAX_API_KEY,启动就报
    "MINIMAX_API_KEY environment variable is required"。
    """
    from app.services.mcp_config import inject_secrets

    monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
    cfg = inject_secrets({"transport": "stdio", "command": "uvx"})
    assert cfg["env"]["MINIMAX_API_KEY"] == "sk-test-key"
    assert "MINIMAX_API_HOST" in cfg["env"]


def test_inject_secrets_keeps_explicit_key(monkeypatch):
    """config 里显式给了 MINIMAX_API_KEY 就不被 LLM_API_KEY 覆盖。"""
    from app.services.mcp_config import inject_secrets

    monkeypatch.setenv("LLM_API_KEY", "sk-from-env")
    cfg = inject_secrets(
        {"transport": "stdio", "command": "uvx", "env": {"MINIMAX_API_KEY": "sk-explicit"}}
    )
    assert cfg["env"]["MINIMAX_API_KEY"] == "sk-explicit"


def test_inject_secrets_does_not_mutate_input(monkeypatch):
    """不修改传入的 dict。"""
    from app.services.mcp_config import inject_secrets

    monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
    src = {"transport": "stdio", "command": "uvx"}
    inject_secrets(src)
    assert "env" not in src


def test_env_loaded_without_importing_core_mcp():
    """只 import mcp_config(不 import app.core.mcp)也要能读到 .env。

    回归:.env 的 load_dotenv 原本只在 app/core/mcp.py 里做(import 副作用),
    任何不 import 那个模块的调用方都拿不到 LLM_API_KEY。

    必须**开子进程**测:同一个 pytest 进程里别的用例可能已经 import 过
    app.core.mcp,把 .env 载进 os.environ 了,那样这个断言就测不出问题。
    子进程是干净的,只 import mcp_config,能真实反映 import 顺序的影响。
    """
    import os
    import subprocess
    import sys

    code = (
        "import os, sys;"
        "sys.path.insert(0, '.');"
        "import app.services.mcp_config as m;"
        "print('HAS_KEY', bool(os.environ.get('LLM_API_KEY')));"
        "print('HAS_HOST', bool(os.environ.get('MINIMAX_API_HOST')))"
    )
    # 子进程会继承父进程的 os.environ —— 父进程(pytest)可能已经因为别的
    # import 把 .env 载进去了,那会把回归盖掉。这里先摘掉这些变量,
    # 让子进程从「干净的、没有 LLM_API_KEY」的状态开始。
    child_env = {
        k: v for k, v in os.environ.items() if k not in ("LLM_API_KEY", "MINIMAX_API_HOST")
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=child_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "HAS_KEY True" in proc.stdout, (
        f"只 import mcp_config 时 os.environ 里应有 LLM_API_KEY;实际输出:\n{proc.stdout}"
    )


def test_describe_error_unwraps_exception_group():
    """_describe_error 要剥到最深层的异常,而不是停在 "1 sub-exception"。"""
    from app.api.routes.mcp import _describe_error

    inner = ValueError("MINIMAX_API_KEY environment variable is required")
    group = ExceptionGroup("unhandled errors in a TaskGroup", [inner])
    assert "MINIMAX_API_KEY" in _describe_error(group)


def test_describe_error_falls_back_to_str():
    """没有子异常时退回 str(exc)。"""
    from app.api.routes.mcp import _describe_error

    assert "boom" in _describe_error(RuntimeError("boom"))
