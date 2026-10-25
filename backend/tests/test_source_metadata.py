"""v11.4:客户端调用信息(source)落库 + 轨迹里能取到。

背景:
  前端每次发消息都带一份 {kind, rpcId, clientTimeZone},后端写进
  user 消息的 meta.source 和 session log 的 user_message 事件,
  轨迹视图的「来源」标签页直接展示。

覆盖:
- 带 source 时,user 消息的 meta_json 里有 source
- 没有 source 时,meta_json 仍是 None
- source 也写进 session.jsonl 的 user_message 事件
- GET /api/sessions/{id} 能拿到 agent_id(轨迹视图的 tool_ids 回退要用)
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import repository as repo
from app.db.base import init_db
from app.db.session import session_scope
from app.main import create_app
from app.services.session_service import create_default_session

SOURCE = {
    "kind": "user",
    "rpcId": "3a459cdc-5241-4a95-92c4-626c0049215c",
    "clientTimeZone": "Asia/Shanghai",
}


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
async def test_source_persisted_in_message_meta():
    """带 source 的这一轮,user 消息的 meta_json 必须含 source。"""
    await init_db()

    async with session_scope() as db:
        sess = await create_default_session(db)

    fake_agent = _make_fake_agent(["好的"])

    with patch(
        "app.services.chat_service.resolve_agent_for_session",
        return_value=fake_agent,
    ):
        from app.services.chat_service import stream_chat

        async with session_scope() as db:
            async for _evt in stream_chat(
                db,
                session_id=sess.id,
                user_message="你好",
                source=dict(SOURCE),
            ):
                pass

    async with session_scope() as db:
        msgs = await repo.list_messages(db, sess.id)

    user_msgs = [m for m in msgs if m.role == "user"]
    assert len(user_msgs) == 1
    meta = json.loads(user_msgs[0].meta_json)
    assert meta["source"] == SOURCE


@pytest.mark.asyncio
async def test_message_without_source_has_no_meta():
    """普通对话(客户端没上报 source)不写 meta —— 不污染老消息。"""
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
    assert user_msgs[0].meta_json is None


@pytest.mark.asyncio
async def test_source_written_to_session_log(tmp_path, monkeypatch):
    """source 也要写进 session.jsonl 的 user_message 事件(轨迹视图读它)。"""
    await init_db()
    monkeypatch.setenv("TRAJECTORY_LOG_DIR", str(tmp_path / "sessions"))

    from app.core.config import get_settings

    settings = get_settings()
    settings.trajectory_log_dir = str(tmp_path / "sessions")

    async with session_scope() as db:
        sess = await create_default_session(db)

    fake_agent = _make_fake_agent(["好的"])

    with patch(
        "app.services.chat_service.resolve_agent_for_session",
        return_value=fake_agent,
    ):
        from app.services.chat_service import stream_chat

        async with session_scope() as db:
            async for _evt in stream_chat(
                db,
                session_id=sess.id,
                user_message="你好",
                source=dict(SOURCE),
            ):
                pass

    from app.trajectory import SessionLogReader

    reader = SessionLogReader(sess.id, root=tmp_path / "sessions")
    traj = await reader.read()
    assert traj.turns
    assert traj.turns[0].user_message_source == SOURCE


@pytest.mark.asyncio
async def test_get_single_session_returns_agent_id():
    """GET /api/sessions/{id} 返回 agent_id(轨迹视图的 tool_ids 回退要用)。"""
    await init_db()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post("/api/sessions", json={"title": "s"})
        sid = r.json()["id"]

        r = await client.get(f"/api/sessions/{sid}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == sid
        assert "agent_id" in body

        r = await client.get("/api/sessions/does-not-exist")
        assert r.status_code == 404
