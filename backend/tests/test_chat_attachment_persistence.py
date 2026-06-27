"""v8.14:stream_chat 持久化附件元信息。

覆盖:
- 流期间探测到 xlsx → file 事件发出 → assistant message 落库时
  meta={"attachments": [{url, filename, mime, size_bytes}, ...]}
- 哪怕 LLM 没产出任何文本,只要产生了附件也要落 assistant 消息
  (否则 list_messages 拿不到附件,刷新后下载按钮还是不显示)
- list_messages 走 /api/sessions/<id>/messages 时,meta 字段被解出
  成 dict 返回,前端 selectSession 拿到后能挂到 m.attachments
- 没附件时 meta=None / 不出现"attachments"键(不污染老消息)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.db.base import init_db
from app.db.session import session_scope
from app.services.session_service import create_default_session

UPLOAD_ROOT = Path("/tmp/swift-agent")
SID = "v814_test_session_001"


# --------------------------------------------------------------------------- #
# 工具:造一个虚拟 supervisor 产出指定 token 流
# --------------------------------------------------------------------------- #


def _chunk(content: str) -> SimpleNamespace:
    return SimpleNamespace(content=content)


def _make_fake_agent(token_chunks: list[str]):
    """返回一个 mock agent,astream_events 异步产出 on_chat_model_stream 事件。"""
    agent = SimpleNamespace()

    async def astream_events(*_args, **_kwargs):
        for txt in token_chunks:
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": _chunk(txt)},
            }

    agent.astream_events = astream_events
    return agent


# --------------------------------------------------------------------------- #
# 1) 端到端:产生附件 → 落库时 meta 里有 attachments
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_chat_persists_attachments_in_meta(tmp_path):
    """v8.14:stream_chat 流期间发出 file 事件,流结束后
    assistant 消息的 meta_json 必须包含 attachments,这样刷新页面后
    list_messages 才能把附件渲染回来。"""
    await init_db()

    # 准备一个真实的 xlsx,让 _detect_file_event 命中
    session_dir = UPLOAD_ROOT / SID
    session_dir.mkdir(parents=True, exist_ok=True)
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"xlsx-bytes-v814")

    try:
        async with session_scope() as db:
            sess = await create_default_session(db)

        # 模拟 stream:前几个 token 没出现 xlsx 路径,出现后 _detect_file_event 命中
        path_str = str(xlsx)
        fake_agent = _make_fake_agent([
            "任务完成。",
            f"已写入 {path_str} ",
            "共 100 行。",
        ])

        with patch(
            "app.services.chat_service.get_supervisor", return_value=fake_agent,
        ):
            from app.services.chat_service import stream_chat

            async with session_scope() as db:
                events = []
                async for evt in stream_chat(
                    db, session_id=sess.id, user_message="hi",
                ):
                    events.append(evt)

        # 1) 流期间至少出现一个 file 事件
        file_events = [e for e in events if e["event"] == "file"]
        assert len(file_events) == 1
        assert file_events[0]["data"]["filename"] == "result.xlsx"
        assert file_events[0]["data"]["size_bytes"] == len(b"xlsx-bytes-v814")

        # 2) 落库的 assistant 消息里 meta 必须含 attachments
        async with session_scope() as db:
            msgs = await repo.list_messages(db, sess.id)
        assistant_msgs = [m for m in msgs if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        meta = json.loads(assistant_msgs[0].meta_json)
        assert "attachments" in meta
        att = meta["attachments"]
        assert len(att) == 1
        assert att[0]["filename"] == "result.xlsx"
        # URL 用的是 stream_chat 收到的 session_id(sess.id 是 create_default_session
        # 生成的 UUID),不是测试硬编码的 SID
        assert att[0]["url"] == f"/api/downloads/{sess.id}/result.xlsx"
        assert att[0]["mime"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 2) 没文本但有附件:仍要落 assistant 消息(否则 list_messages 拿不到)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_chat_persists_attachment_only_message(tmp_path):
    """v8.14:LLM 只输出 xlsx 路径(没自然语言文本)时,stream_chat 也得
    落一条 assistant 消息,否则附件没有归属的 message row,
    list_messages 返回的消息列表里没这条 → 刷新后下载按钮没地方渲染。"""
    await init_db()

    session_dir = UPLOAD_ROOT / SID
    session_dir.mkdir(parents=True, exist_ok=True)
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"x")

    try:
        async with session_scope() as db:
            sess = await create_default_session(db)

        # 流内容:只含 xlsx 路径,无其他文字 → full_text 为 "saved ...xlsx"
        # 但理论上 _detect_file_event 也会把这种纯路径也认出来
        fake_agent = _make_fake_agent([f"saved {xlsx}"])

        with patch(
            "app.services.chat_service.get_supervisor", return_value=fake_agent,
        ):
            from app.services.chat_service import stream_chat

            async with session_scope() as db:
                events = []
                async for evt in stream_chat(
                    db, session_id=sess.id, user_message="go",
                ):
                    events.append(evt)

        # 流事件:file 事件 + done
        file_events = [e for e in events if e["event"] == "file"]
        assert len(file_events) == 1

        # 关键断言:即便 full_text 几乎只有 xlsx 路径,assistant 消息也必须存在
        async with session_scope() as db:
            msgs = await repo.list_messages(db, sess.id)
        assistant_msgs = [m for m in msgs if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert "xlsx" in assistant_msgs[0].content  # full_text 也被存了
        meta = json.loads(assistant_msgs[0].meta_json)
        assert meta["attachments"][0]["filename"] == "result.xlsx"
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 3) 没有任何附件:meta=None(老消息/普通对话不受影响)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_chat_no_attachment_meta_is_none():
    """v8.14:LLM 没产生附件(普通问答)时,meta 必须为 None。
    不污染老 schema,后端 list_messages 看到 None → meta=None。"""
    await init_db()

    async with session_scope() as db:
        sess = await create_default_session(db)

    fake_agent = _make_fake_agent(["你好", ",", "世界"])

    with patch(
        "app.services.chat_service.get_supervisor", return_value=fake_agent,
    ):
        from app.services.chat_service import stream_chat

        async with session_scope() as db:
            events = []
            async for evt in stream_chat(
                db, session_id=sess.id, user_message="hi",
            ):
                events.append(evt)

    file_events = [e for e in events if e["event"] == "file"]
    assert file_events == []  # 没有 xlsx 路径,不发 file 事件

    async with session_scope() as db:
        msgs = await repo.list_messages(db, sess.id)
    assistant_msgs = [m for m in msgs if m.role == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].meta_json is None  # 没附件就不写 meta


# --------------------------------------------------------------------------- #
# 4) list_messages 解码 meta_json → meta dict(供前端 selectSession 读)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_messages_returns_meta_dict_with_attachments():
    """v8.14:GET /api/sessions/<id>/messages 必须把 meta_json 解码成
    dict,前端 selectSession 才能 m.meta?.attachments 拿到附件列表。"""
    from app.api.routes.messages import list_messages as route_list_messages

    await init_db()
    async with session_scope() as db:
        sess = await create_default_session(db)
        await repo.append_message(
            db,
            session_id=sess.id,
            role="assistant",
            content="done",
            meta={"attachments": [{
                "url": "/api/downloads/x/r.xlsx",
                "filename": "r.xlsx",
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size_bytes": 123,
            }]},
        )

    # 直接调路由函数(注入 db fixture)
    factory = await _get_factory()
    async with factory() as db:
        out = await route_list_messages(sess.id, db)

    assert len(out) == 1
    assert out[0].meta is not None
    assert "attachments" in out[0].meta
    assert out[0].meta["attachments"][0]["filename"] == "r.xlsx"
    assert out[0].meta["attachments"][0]["size_bytes"] == 123


async def _get_factory():
    from app.db.base import get_session_factory
    return get_session_factory()
