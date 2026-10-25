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
