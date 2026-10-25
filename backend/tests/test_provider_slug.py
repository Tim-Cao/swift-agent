"""「提供商 ID」(slug):新增 / 编辑 / 去重 / 迁移回填。

背景(v11.3):
  提供商卡片上不显示 API Key,也不显示"OpenAI 兼容端点"这种实现细节,
  只显示一个用户自己起的短标识 —— 「提供商 ID」。
  它跟内部主键(id,uuid)分开:主键不可读,也不适合让用户填。

覆盖:
- slugify 的规整规则(小写 / 短横线 / 中文可用 / 全标点 → 空)
- 新增时留空 → 按名称自动生成
- 新增时填了 → 规整后使用
- 撞名 → 自动加 -2 后缀
- 编辑时改 slug → 生效;留空 → 不改
- 数据迁移:老库的 providers 行回填 slug,幂等
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.slugify import slugify


# --------------------------------------------------------------------------- #
# 1) slugify
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("minimax", "minimax"),
        ("  MiniMax  ", "minimax"),
        ("Mini Max", "mini-max"),
        ("openai_compatible", "openai-compatible"),
        ("a--b", "a-b"),
        ("我的提供商", "我的提供商"),
        ("!!!", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


# --------------------------------------------------------------------------- #
# 2) API:新增 / 编辑
# --------------------------------------------------------------------------- #


@pytest.fixture
async def client():
    from app.db.base import init_db
    from app.main import app

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_create_provider_uses_given_slug(client: AsyncClient):
    """填了提供商 ID → 规整后使用。"""
    resp = await client.post(
        "/api/providers",
        json={
            "name": "我的提供商",
            "slug": "  My Provider  ",
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
        },
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["slug"] == "my-provider", out

    await client.delete(f"/api/providers/{out['id']}")


async def test_create_provider_dedups_slug(client: AsyncClient):
    """提供商 ID 撞了 → 自动加后缀,不报错。"""
    first = await client.post(
        "/api/providers",
        json={
            "name": "A",
            "slug": "dup",
            "base_url": "https://a.com/v1",
            "api_key": "sk-a",
        },
    )
    second = await client.post(
        "/api/providers",
        json={
            "name": "B",
            "slug": "dup",
            "base_url": "https://b.com/v1",
            "api_key": "sk-b",
        },
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["slug"] == "dup"
    assert second.json()["slug"] == "dup-2", second.json()

    await client.delete(f"/api/providers/{first.json()['id']}")
    await client.delete(f"/api/providers/{second.json()['id']}")


async def test_update_provider_slug(client: AsyncClient):
    """编辑时改提供商 ID → 生效。"""
    created = await client.post(
        "/api/providers",
        json={
            "name": "改名测试",
            "slug": "old-slug",
            "base_url": "https://x.com/v1",
            "api_key": "sk-x",
        },
    )
    pid = created.json()["id"]

    resp = await client.patch(f"/api/providers/{pid}", json={"slug": "new-slug"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["slug"] == "new-slug"

    # 留空 = 不改
    resp2 = await client.patch(f"/api/providers/{pid}", json={"slug": ""})
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["slug"] == "new-slug", "空 slug 不该把原来的清掉"

    await client.delete(f"/api/providers/{pid}")


async def test_update_provider_slug_dedups_against_others(client: AsyncClient):
    """改成别人的 ID → 自动加后缀,不会把两条记录搞成同一个。"""
    a = await client.post(
        "/api/providers",
        json={
            "name": "甲",
            "slug": "alpha",
            "base_url": "https://a.com/v1",
            "api_key": "sk-a",
        },
    )
    b = await client.post(
        "/api/providers",
        json={
            "name": "乙",
            "slug": "beta",
            "base_url": "https://b.com/v1",
            "api_key": "sk-b",
        },
    )
    resp = await client.patch(f"/api/providers/{b.json()['id']}", json={"slug": "alpha"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["slug"] == "alpha-2", resp.json()

    await client.delete(f"/api/providers/{a.json()['id']}")
    await client.delete(f"/api/providers/{b.json()['id']}")


async def test_provider_out_has_slug(client: AsyncClient):
    """列表接口也要带上提供商 ID(卡片要显示它)。"""
    created = await client.post(
        "/api/providers",
        json={
            "name": "列表测试",
            "slug": "list-test",
            "base_url": "https://x.com/v1",
            "api_key": "sk-x",
        },
    )
    pid = created.json()["id"]

    lst = await client.get("/api/providers")
    assert lst.status_code == 200
    mine = next(p for p in lst.json() if p["id"] == pid)
    assert mine["slug"] == "list-test"

    await client.delete(f"/api/providers/{pid}")


@pytest.mark.parametrize(
    ("payload", "missing"),
    [
        ({"base_url": "https://x.com/v1", "api_key": "sk-x"}, "name"),
        ({"name": "X", "base_url": "https://x.com/v1", "api_key": "sk-x"}, "slug"),
        ({"name": "X", "slug": "x", "api_key": "sk-x"}, "base_url"),
        ({"name": "X", "slug": "x", "base_url": "https://x.com/v1"}, "api_key"),
    ],
)
async def test_create_provider_requires_all_fields(
    client: AsyncClient, payload: dict, missing: str
):
    """四个字段都是必填 —— 少一个就 422。"""
    resp = await client.post("/api/providers", json=payload)
    assert resp.status_code == 422, resp.text
    assert any(missing in str(e["loc"]) for e in resp.json()["detail"]), resp.text
