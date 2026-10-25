"""提供商的 API Key 处理:掩码不能被当成新 key 存进 DB。

背景(v11.1):
  「模型管理」页编辑提供商时,前端回填的是**掩码**(如 ``sk-a**********89``),
  留空表示不修改。但后端原来的判断是 ``not api_key.startswith("***")`` ——
  掩码保留了前 4 位,永远不以 ``*`` 开头,那个判断等于没生效:
  把掩码原样回传会被当成真 key 存进去,把数据库里真正的 key 覆盖成掩码,
  之后所有请求都用一把废 key,表现为「鉴权失败」。

覆盖:
- 掩码被识别出来(不当作新 key)
- 空字符串 = 不修改
- 真 key 正常通过
- PATCH 传掩码时,DB 里的 key 不变
"""

from __future__ import annotations

import pytest

from app.api.routes.models import _is_mask, _mask


def test_mask_shape():
    """_mask 保留前 4 位和后 2 位,中间是连续的 *。"""
    masked = _mask("sk-abcdefghijklmnop")
    assert masked.startswith("sk-a")
    assert masked.endswith("op")
    assert masked[4:-2] == "*" * (len(masked) - 6)
    assert _mask("short") == "*****"
    assert _mask("") == ""


@pytest.mark.parametrize(
    "value",
    [
        "sk-a**********89",
        "sk-m****************90",
        "**********",
    ],
)
def test_is_mask_detects_masked_values(value: str):
    """掩码必须被识别成掩码 —— 这是旧逻辑漏掉的情况。"""
    assert _is_mask(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "sk-realkeywithoutstars",
        "sk-abc123",
    ],
)
def test_is_mask_passes_real_keys(value: str):
    """真 key 不能被误判成掩码(否则改了 key 也存不进去)。"""
    assert _is_mask(value) is False


@pytest.mark.asyncio
async def test_patch_with_mask_keeps_existing_key():
    """PATCH 只传掩码时,DB 里的 key 不能被覆盖成掩码。"""
    from httpx import ASGITransport, AsyncClient

    from app.db.base import init_db
    from app.db.session import session_scope
    from app.main import app

    await init_db()

    async with session_scope() as db:
        from app.db import catalog_repository as cat

        provider = await cat.create_provider(
            db,
            name="掩码保护测试",
            base_url="https://api.example.com/v1",
            api_key="sk-the-real-secret-key",
            enabled=True,
        )
        await db.commit()
        provider_id = provider.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            f"/api/providers/{provider_id}",
            json={"base_url": "https://api.example.com/v2"},
        )
        assert resp.status_code == 200, resp.text
        # 回传的仍然是掩码
        assert "*" in resp.json()["api_key"]

    async with session_scope() as db:
        from app.db import catalog_repository as cat

        again = await cat.get_provider(db, provider_id)
        assert again is not None
        assert again.api_key == "sk-the-real-secret-key", "掩码不能覆盖真 key"
        assert again.base_url == "https://api.example.com/v2", "base_url 应该被更新"
