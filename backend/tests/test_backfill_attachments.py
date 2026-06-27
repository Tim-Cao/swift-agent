"""v8.14.1:backfill_message_attachments 脚本的回填行为。

覆盖:
- 历史消息 content 含 xlsx 路径 + 文件真实存在 → 回填 meta_json['attachments']
- content 没 xlsx 路径 → 跳过,meta_json 不动
- 文件已被删(/tmp 清掉)→ 跳过(避免点下载 404)
- 已经回填过的(已有 attachments 键)→ 跳过(幂等)
- 没 meta_json 的消息(content 有 xlsx)→ 写一个新的 meta_json={'attachments': [...]}
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import models
from app.db import repository as repo
from app.db.base import init_db
from app.db.session import session_scope
from app.services.session_service import create_default_session
from scripts.backfill_message_attachments import (
    backfill_once,
    extract_attachments_from_content,
)

UPLOAD_ROOT = Path("/tmp/swift-agent")
SID = "v8141_test_session"


@pytest.fixture
def session_dir():
    d = UPLOAD_ROOT / SID
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 1) extract_attachments_from_content 单元测试
# --------------------------------------------------------------------------- #


def test_extract_finds_existing_xlsx(session_dir):
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"abc")
    text = f"已生成 {xlsx} 共 10 行"
    atts = extract_attachments_from_content(text, SID)
    assert len(atts) == 1
    assert atts[0]["filename"] == "result.xlsx"
    assert atts[0]["url"] == f"/api/downloads/{SID}/result.xlsx"
    assert atts[0]["size_bytes"] == 3
    assert atts[0]["mime"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_extract_skips_missing_xlsx(session_dir):
    """xlsx 路径在文本里但文件已删 → 不返回,避免 404。"""
    text = f"saved /tmp/swift-agent/{SID}/ghost.xlsx"
    atts = extract_attachments_from_content(text, SID)
    assert atts == []


def test_extract_handles_private_tmp_form(session_dir):
    """macOS resolved 路径 /private/tmp/... 也必须能匹配。"""
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"x")
    private_form = str(xlsx).replace("/tmp/", "/private/tmp/", 1)
    text = f"saved to {private_form}"
    atts = extract_attachments_from_content(private_form, SID)
    assert len(atts) == 1


def test_extract_empty_or_none():
    assert extract_attachments_from_content(None, SID) == []
    assert extract_attachments_from_content("", SID) == []
    assert extract_attachments_from_content("无附件", SID) == []


# --------------------------------------------------------------------------- #
# 2) backfill_once 端到端(走真实 DB)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_backfill_writes_attachments_for_message_with_xlsx(session_dir):
    """content 含 xlsx 路径 + 文件真实存在 → 回填 meta_json。"""
    await init_db()
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"xlsx-data")

    async with session_scope() as db:
        sess = await create_default_session(db)
        # 模拟 v8.14 之前的 assistant 消息:有 content,无 meta_json
        m = await repo.append_message(
            db, session_id=sess.id, role="assistant",
            content=f"已完成,见 {xlsx}",
        )
        msg_id = m.id

    stats = await backfill_once()
    assert stats["backfilled"] == 1
    assert stats["scanned"] >= 1
    assert stats["skipped_already_filled"] == 0

    async with session_scope() as db:
        row = await db.get(models.Message, msg_id)
    assert row.meta_json is not None
    meta = json.loads(row.meta_json)
    assert "attachments" in meta
    assert len(meta["attachments"]) == 1
    assert meta["attachments"][0]["filename"] == "result.xlsx"


@pytest.mark.asyncio
async def test_backfill_skips_message_without_xlsx():
    """content 没 xlsx 路径 → 不动 meta_json。"""
    await init_db()
    async with session_scope() as db:
        sess = await create_default_session(db)
        m = await repo.append_message(
            db, session_id=sess.id, role="assistant",
            content="普通回答,无附件",
        )
        msg_id = m.id

    stats = await backfill_once()
    assert stats["no_xlsx"] >= 1

    async with session_scope() as db:
        row = await db.get(models.Message, msg_id)
    assert row.meta_json is None  # 没附件就不写


@pytest.mark.asyncio
async def test_backfill_skips_xlsx_with_missing_file():
    """content 有 xlsx 路径但文件已删 → 不写 meta_json(避免用户点 404)。"""
    await init_db()
    ghost_path = f"/tmp/swift-agent/{SID}/gone.xlsx"
    async with session_scope() as db:
        sess = await create_default_session(db)
        m = await repo.append_message(
            db, session_id=sess.id, role="assistant",
            content=f"saved to {ghost_path}",
        )
        msg_id = m.id

    stats = await backfill_once()
    # 不会被 backfilled(因为文件不存在)
    async with session_scope() as db:
        row = await db.get(models.Message, msg_id)
    assert row.meta_json is None
    assert stats["backfilled"] == 0


@pytest.mark.asyncio
async def test_backfill_is_idempotent(session_dir):
    """v8.14 之后生成的消息已有 meta_json['attachments'] → 跳过不重写。"""
    await init_db()
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"x")

    async with session_scope() as db:
        sess = await create_default_session(db)
        # 模拟 v8.14 之后的消息(已有 meta)
        m = await repo.append_message(
            db, session_id=sess.id, role="assistant",
            content=f"saved to {xlsx}",
            meta={"attachments": [{
                "url": "/api/downloads/old/old.xlsx",
                "filename": "old.xlsx",
                "mime": "...",
                "size_bytes": 999,
            }]},
        )
        msg_id = m.id
        original_meta = m.meta_json

    stats = await backfill_once()
    # 已有 attachments → 跳过
    async with session_scope() as db:
        row = await db.get(models.Message, msg_id)
    # meta_json 不变(老的 url 还在)
    assert row.meta_json == original_meta
    assert stats["skipped_already_filled"] >= 1


@pytest.mark.asyncio
async def test_backfill_preserves_existing_meta_keys(session_dir):
    """如果 meta_json 已有其他键(非 attachments),回填要保留它们,只加 attachments。"""
    await init_db()
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"x")

    async with session_scope() as db:
        sess = await create_default_session(db)
        # 假设别的业务写了 {"source": "intake", "tokens": 100},没 attachments
        m = await repo.append_message(
            db, session_id=sess.id, role="assistant",
            content=f"saved to {xlsx}",
            meta={"source": "intake", "tokens": 100},
        )
        msg_id = m.id

    await backfill_once()

    async with session_scope() as db:
        row = await db.get(models.Message, msg_id)
    meta = json.loads(row.meta_json)
    # 老键保留
    assert meta["source"] == "intake"
    assert meta["tokens"] == 100
    # 新键加入
    assert "attachments" in meta
    assert meta["attachments"][0]["filename"] == "result.xlsx"
