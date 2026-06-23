"""v8.2:chat_service._map_event 流式事件映射。

覆盖 on_chat_model_stream 的 content 形态兼容:
- str:正常流式
- list[dict]:OpenAI 工具调用增量格式,text 段拼成 token
- 空 / 纯 tool_use 段:不发 token(避免误把工具调用 ID 当字)
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.chat_service import _map_event


def _chunk(content):
    return SimpleNamespace(content=content)


def test_map_stream_str_content():
    raw = {"event": "on_chat_model_stream", "data": {"chunk": _chunk("你好")}}
    out = _map_event(raw)
    assert out == {"event": "token", "data": {"content": "你好"}}


def test_map_stream_list_text_segments():
    """list 形态:把 type=='text' 的段拼起来当 token。"""
    raw = {
        "event": "on_chat_model_stream",
        "data": {
            "chunk": _chunk([
                {"type": "text", "text": "你好"},
                {"type": "text", "text": "世界"},
            ]),
        },
    }
    out = _map_event(raw)
    assert out == {"event": "token", "data": {"content": "你好世界"}}


def test_map_stream_list_only_tool_use_returns_none():
    """list 里只有 tool_use 段,没有 text → 不发 token(由 on_tool_* 负责)。"""
    raw = {
        "event": "on_chat_model_stream",
        "data": {
            "chunk": _chunk([
                {"type": "tool_use", "id": "abc", "name": "x"},
            ]),
        },
    }
    assert _map_event(raw) is None


def test_map_stream_mixed_text_and_tool_use():
    """text + tool_use 混在一起,只把 text 拼成 token。"""
    raw = {
        "event": "on_chat_model_stream",
        "data": {
            "chunk": _chunk([
                {"type": "text", "text": "先说"},
                {"type": "tool_use", "id": "x"},
                {"type": "text", "text": "两句"},
            ]),
        },
    }
    out = _map_event(raw)
    assert out == {"event": "token", "data": {"content": "先说两句"}}


def test_map_stream_empty_content_returns_none():
    assert _map_event({"event": "on_chat_model_stream", "data": {"chunk": _chunk("")}}) is None
    assert _map_event({"event": "on_chat_model_stream", "data": {"chunk": _chunk([])}}) is None
    assert _map_event({"event": "on_chat_model_stream", "data": {"chunk": _chunk(None)}}) is None


def test_map_stream_unrelated_event_returns_none():
    """on_chain_start / on_chain_end 等 → None。"""
    assert _map_event({"event": "on_chain_start", "data": {}}) is None
    assert _map_event({"event": "on_chain_end", "data": {}}) is None


def test_map_tool_start_event_silenced():
    """v8.4:on_tool_start 不再产生 tool_call 事件(前端用不到且会刷屏)。"""
    raw = {"event": "on_tool_start", "data": {"name": "write_excel", "input": {"x": 1}}}
    assert _map_event(raw) is None


def test_map_tool_end_event_silenced():
    """v8.4:on_tool_end 不再产生 tool_result 事件(xlsx 路径检测在
    stream_chat 的 _detect_file_event 里另走 file 事件通道)。"""
    raw = {
        "event": "on_tool_end",
        "data": {
            "name": "write_excel",
            "output": "saved /tmp/swift-agent/x/result.xlsx",
        },
    }
    assert _map_event(raw) is None
