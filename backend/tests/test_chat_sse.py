"""聊天相关 schema / supervisor 配置的轻量单测(StreamEvent 已删除,改为 dict 透传)。"""

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


def test_app_context_dataclass():
    """AppContext 是 dataclass,可作为 deepagents context_schema。"""
    from app.supervisor.context import AppContext

    ctx = AppContext(session_id="s1", user_id="u1", tenant="t1")
    assert ctx.session_id == "s1"
    assert ctx.user_id == "u1"
    assert ctx.tenant == "t1"


def test_make_thread_config():
    from app.supervisor.builder import make_thread_config

    cfg = make_thread_config("thread-42")
    assert cfg == {"configurable": {"thread_id": "thread-42"}}
