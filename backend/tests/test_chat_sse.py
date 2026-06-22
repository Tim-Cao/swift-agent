"""聊天相关 schema / supervisor 配置的轻量单测。"""

from __future__ import annotations

from app.schemas.chat import ChatRequest


def test_chat_request_min():
    r = ChatRequest(message="hi")
    assert r.message == "hi"
    assert r.session_id is None
    assert r.agent_name is None


def test_chat_request_full():
    r = ChatRequest(message="hi", session_id="abc", agent_name="default")
    assert r.session_id == "abc"
    assert r.agent_name == "default"


def test_chat_request_rejects_empty():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_make_thread_config():
    from app.supervisor.builder import make_thread_config

    cfg = make_thread_config("thread-42")
    assert cfg == {"configurable": {"thread_id": "thread-42"}}
