"""上传的 zip 工具包:新建 / 替换实现。

背景(v11.2):
  「上传 zip」从工具列表页的一个独立按钮,挪进了「新建 / 编辑工具」弹窗里,
  变成一块可拖拽的上传区。于是后端要支持**替换**已有工具的实现:
  工具名不变(agent 的工具绑定不能因为换了 zip 就失效),只换代码。

覆盖:
- 替换后工具的 id / name 不变,显示名 / 描述按传入的更新
- 替换的 zip 里注册了别的工具名 → 400,且不改动原有工具
- 内置工具不允许替换 → 400
- 新建(不带 replace_tool_id)时,显示名 / 描述可以用前端传的值覆盖
"""

from __future__ import annotations

import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.base import init_db
from app.db.session import session_scope
from app.main import app


def _make_zip(tool_name: str, body: str = "return 1") -> bytes:
    """造一个只含一个 .py 模块的 zip,模块里注册名为 tool_name 的工具。"""
    src = (
        "from langchain_core.tools import tool\n"
        "from tools import register_tool\n"
        "\n"
        "@tool\n"
        f"def {tool_name}() -> str:\n"
        f'    """{tool_name} 的说明"""\n'
        f'    return "{body}"\n'
        "\n"
        f'register_tool("{tool_name}", {tool_name}, display_name="{tool_name}")\n'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{tool_name}.py", src)
    return buf.getvalue()


@pytest.fixture(autouse=True)
async def _db():
    await init_db()
    # init_db 只建表;内置工具要 seed 才有(前端能看到 builtin=True 的那些)
    from app.db.seed import seed_tools

    async with session_scope() as db:
        await seed_tools(db)
        await db.commit()


async def _upload(client: AsyncClient, filename: str, data: bytes, **fields) -> dict:
    return await client.post(
        "/api/tools/upload",
        files={"file": (filename, data, "application/zip")},
        data=fields or None,
    )


@pytest.mark.asyncio
async def test_upload_creates_tool_with_frontend_display_name():
    """新建时前端传的显示名 / 描述优先于 zip 里 register_tool 的默认值。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await _upload(
            client,
            "pkg.zip",
            _make_zip("my_greet_tool"),
            display_name="打个招呼",
            description="前端指定的描述",
        )
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert len(out) == 1
        assert out[0]["name"] == "my_greet_tool"
        assert out[0]["display_name"] == "打个招呼"
        assert out[0]["description"] == "前端指定的描述"
        assert out[0]["builtin"] is False

        # 清理
        await client.delete(f"/api/tools/{out[0]['id']}")


@pytest.mark.asyncio
async def test_replace_keeps_id_and_name_updates_code():
    """替换实现:工具 id / name 不变,显示名 / 描述按传入的更新。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _upload(client, "pkg.zip", _make_zip("my_replace_tool"))
        assert created.status_code == 200, created.text
        tool = created.json()[0]
        tool_id = tool["id"]

        replaced = await _upload(
            client,
            "pkg2.zip",
            _make_zip("my_replace_tool", body="return 2"),
            replace_tool_id=tool_id,
            display_name="新显示名",
        )
        assert replaced.status_code == 200, replaced.text
        out = replaced.json()[0]

        assert out["id"] == tool_id, "替换不能换 id(agent 的工具绑定会失效)"
        assert out["name"] == "my_replace_tool", "替换不能换名字"
        assert out["display_name"] == "新显示名"

        # 工具在列表里还是同一个
        lst = await client.get("/api/tools")
        ids = [t["id"] for t in lst.json() if t["name"] == "my_replace_tool"]
        assert ids == [tool_id], "不该出现第二条同名记录"

        await client.delete(f"/api/tools/{tool_id}")


@pytest.mark.asyncio
async def test_replace_keeps_old_display_name_when_not_given():
    """替换时没传显示名 → 沿用旧值(不覆盖成 zip 里的默认值)。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _upload(
            client, "pkg.zip", _make_zip("my_keep_tool"), display_name="原来的名字"
        )
        tool = created.json()[0]

        replaced = await _upload(
            client,
            "pkg2.zip",
            _make_zip("my_keep_tool", body="return 2"),
            replace_tool_id=tool["id"],
        )
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()[0]["display_name"] == "原来的名字"

        await client.delete(f"/api/tools/{tool['id']}")


@pytest.mark.asyncio
async def test_replace_with_different_tool_name_is_rejected():
    """zip 里注册的工具名跟要替换的对不上 → 400,原工具不受影响。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _upload(client, "pkg.zip", _make_zip("my_orig_tool"))
        tool = created.json()[0]

        resp = await _upload(
            client,
            "other.zip",
            _make_zip("my_other_tool"),
            replace_tool_id=tool["id"],
        )
        assert resp.status_code == 400, resp.text
        assert "不一致" in resp.json()["detail"]

        # 原工具还在,没被动过
        got = await client.get(f"/api/tools/{tool['id']}")
        assert got.status_code == 200
        assert got.json()["name"] == "my_orig_tool"

        await client.delete(f"/api/tools/{tool['id']}")


@pytest.mark.asyncio
async def test_cannot_replace_builtin_tool():
    """内置工具的代码在仓库里,不允许用 zip 替换。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        lst = await client.get("/api/tools")
        builtin = next(t for t in lst.json() if t["builtin"])

        resp = await _upload(
            client,
            "pkg.zip",
            _make_zip(builtin["name"]),
            replace_tool_id=builtin["id"],
        )
        assert resp.status_code == 400, resp.text
        assert "内置工具" in resp.json()["detail"]
