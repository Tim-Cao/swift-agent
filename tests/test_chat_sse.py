"""聊天接口测试(StreamEvent + stream_chat 降级路径)。"""

from __future__ import annotations

import pytest

from app.schemas.chat import StreamEvent


def test_stream_event_valid():
    e = StreamEvent(type="token", content="hi")
    assert e.type == "token"
    assert e.content == "hi"
    assert e.meta is None


def test_stream_event_done():
    e = StreamEvent(type="done", meta={"session_id": "abc"})
    assert e.type == "done"
    assert e.meta == {"session_id": "abc"}


def test_stream_event_error():
    e = StreamEvent(type="error", content="oops")
    assert e.type == "error"
    assert e.content == "oops"
