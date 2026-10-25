"""用户上传的文件要落进 user 消息的 meta.attachments。

背景(v11.1):
  以前上传的 zip 只存在于输入框上方的 chip 里,发完消息就没了 ——
  刷新页面看不到「这轮上传过什么文件」。现在前端把附件描述随 ChatRequest
  一起发上来,后端写进 user 消息的 meta_json,前端气泡里渲染成文件卡。

覆盖:
- 带 attachment 时,user 消息的 meta_json 里有 attachments
- 没有 attachment 时,meta_json 仍是 None(不污染普通对话)
- 上传目录前缀 [UPLOAD_DIR:...] **不落库**(落库的应是用户原话)
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.db import repository as repo
from app.db.base import init_db
from app.db.session import session_scope
from app.services.session_service import create_default_session


def _make_fake_agent(token_chunks: list[str]):
    agent = SimpleNamespace()

    async def astream_events(*_args, **_kwargs):
        for txt in token_chunks:
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": SimpleNamespace(content=txt)},
            }

    agent.astream_events = astream_events
    return agent


@pytest.mark.asyncio
async def test_user_attachment_persisted_in_meta():
    """带 attachment 的这一轮,user 消息的 meta_json 必须含 attachments。"""
    await init_db()

    async with session_scope() as db:
        sess = await create_default_session(db)

    fake_agent = _make_fake_agent(["好的", ",", "收到"])

    with patch(
        "app.services.chat_service.resolve_agent_for_session",
        return_value=fake_agent,
    ):
        from app.services.chat_service import stream_chat

        async with session_scope() as db:
            async for _evt in stream_chat(
                db,
                session_id=sess.id,
                user_message="帮我处理这个 zip",
                upload_dir="/tmp/swift-agent/abc/csv",
                attachment={
                    "name": "sales.zip",
                    "size_bytes": 2048,
                    "csv_count": 3,
                },
            ):
                pass

    async with session_scope() as db:
        msgs = await repo.list_messages(db, sess.id)

    user_msgs = [m for m in msgs if m.role == "user"]
    assert len(user_msgs) == 1
    meta = json.loads(user_msgs[0].meta_json)
    assert "attachments" in meta
    att = meta["attachments"][0]
    assert att["name"] == "sales.zip"
    assert att["size_bytes"] == 2048
    assert att["csv_count"] == 3


@pytest.mark.asyncio
async def test_user_message_without_attachment_has_no_meta():
    """普通对话(没上传文件)不写 meta —— 不污染老消息。"""
    await init_db()

    async with session_scope() as db:
        sess = await create_default_session(db)

    fake_agent = _make_fake_agent(["你好"])

    with patch(
        "app.services.chat_service.resolve_agent_for_session",
        return_value=fake_agent,
    ):
        from app.services.chat_service import stream_chat

        async with session_scope() as db:
            async for _evt in stream_chat(
                db, session_id=sess.id, user_message="你好",
            ):
                pass

    async with session_scope() as db:
        msgs = await repo.list_messages(db, sess.id)

    user_msgs = [m for m in msgs if m.role == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0].meta_json is None


@pytest.mark.asyncio
async def test_upload_dir_prefix_not_persisted():
    """[UPLOAD_DIR:...] 只是给 LLM 看的,落库的必须是用户原话。"""
    await init_db()

    async with session_scope() as db:
        sess = await create_default_session(db)

    fake_agent = _make_fake_agent(["收到"])

    with patch(
        "app.services.chat_service.resolve_agent_for_session",
        return_value=fake_agent,
    ):
        from app.services.chat_service import stream_chat

        async with session_scope() as db:
            async for _evt in stream_chat(
                db,
                session_id=sess.id,
                user_message="帮我处理这个 zip",
                upload_dir="/tmp/swift-agent/abc/csv",
            ):
                pass

    async with session_scope() as db:
        msgs = await repo.list_messages(db, sess.id)

    user_msgs = [m for m in msgs if m.role == "user"]
    assert user_msgs[0].content == "帮我处理这个 zip"
    assert "UPLOAD_DIR" not in user_msgs[0].content
