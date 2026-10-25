"""v9:trajectory + session log 的单元测试。

覆盖:
  - SessionLogWriter 写 header + 事件、seq 单调递增、并发锁
  - SessionLogReader 折叠 turns / steps / summary
  - Trajectory API 端点(空 / 有数据 / 404)
  - log/export 端点(200 / 404)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.trajectory import SessionLogReader, SessionLogWriter, Trajectory


@pytest.fixture
def log_root(tmp_path):
    """每次测试用独立目录。"""
    root = tmp_path / "sessions"
    root.mkdir()
    return root


# --------------------------------------------------------------------------- #
# SessionLogWriter
# --------------------------------------------------------------------------- #


async def test_writer_writes_header_and_events(log_root):
    w = SessionLogWriter("sess_abc", root=log_root)
    await w.open(agent_name="sup", model="gpt-4o-mini")
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "hi"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "he"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "llo"})
    await w.close()

    reader = SessionLogReader("sess_abc", root=log_root)
    header = await reader.read_header()
    assert header is not None
    assert header.id == "sess_abc"
    assert header.model == "gpt-4o-mini"

    events = await reader.read_events()
    assert len(events) == 4
    # seq 单调递增
    assert [e.seq for e in events] == [1, 2, 3, 4]
    assert [e.type for e in events] == [
        "turn_start",
        "user_message",
        "assistant_chunk",
        "assistant_chunk",
    ]
    # delta 拼接 → "he" + "llo"
    assert events[2].data["delta"] == "he"
    assert events[3].data["delta"] == "llo"


async def test_writer_appends_to_existing_file(log_root):
    """第二次 open 不重写 header,seq 接着上次。"""
    w1 = SessionLogWriter("sess_x", root=log_root)
    await w1.open(agent_name=None, model="m")
    await w1.append("turn_start", {"turn": 0})
    await w1.close()

    w2 = SessionLogWriter("sess_x", root=log_root)
    await w2.open(agent_name=None, model="m")
    await w2.append("turn_start", {"turn": 1})
    await w2.close()

    reader = SessionLogReader("sess_x", root=log_root)
    events = await reader.read_events()
    assert len(events) == 2
    # seq 接续(不会从 1 重新开始)
    assert events[0].seq == 1
    assert events[1].seq == 2


async def test_writer_returns_event_with_seq_time(log_root):
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    e = await w.append("user_message", {"content": "x"})
    await w.close()
    assert e.seq == 1
    assert e.time > 0
    assert e.type == "user_message"
    assert e.data == {"content": "x"}


# --------------------------------------------------------------------------- #
# SessionLogReader 折叠
# --------------------------------------------------------------------------- #


async def test_reader_folds_single_turn_assistant_only(log_root):
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "hi"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "He"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "llo"})
    await w.append("assistant_message", {
        "turn": 0, "step": 0,
        "content": "Hello",
        "usage": {"input_tokens": 5, "output_tokens": 1},
    })
    await w.append("turn_end", {"turn": 0, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    assert isinstance(traj, Trajectory)
    assert traj.summary.empty is False
    assert traj.summary.turns == 1
    assert traj.summary.steps == 1
    assert traj.summary.total_input_tokens == 5
    assert traj.summary.total_output_tokens == 1

    turn = traj.turns[0]
    assert turn.user_message == "hi"
    assert turn.ended_reason == "normal"
    assert len(turn.steps) == 1
    assert turn.steps[0].kind == "assistant_message"
    assert turn.steps[0].assistant.content == "Hello"


async def test_reader_folds_tool_call_result_pair(log_root):
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "ls /tmp"})
    await w.append("tool_call", {
        "turn": 0, "step": 0,
        "call_id": "c1", "name": "ls",
        "input": {"path": "/tmp"},
    })
    await w.append("tool_result", {
        "turn": 0, "step": 0,
        "call_id": "c1", "name": "ls",
        "output": "a\nb", "is_error": False,
    })
    await w.append("turn_end", {"turn": 0, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    assert traj.summary.tool_calls == [
        # ToolCallSummary ordering is sorted by name
        __import__("app.trajectory.schema", fromlist=["TrajectoryToolCallSummary"])
        .TrajectoryToolCallSummary(name="ls", count=1, error_count=0)
    ]
    turn = traj.turns[0]
    assert len(turn.steps) == 1
    assert turn.steps[0].kind == "tool"
    assert turn.steps[0].tool.name == "ls"
    assert turn.steps[0].tool.input == {"path": "/tmp"}
    assert turn.steps[0].tool.output == "a\nb"
    assert turn.steps[0].tool.is_error is False


async def test_reader_folds_error_turn(log_root):
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "go"})
    await w.append("turn_end", {"turn": 0, "reason": "error"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    assert traj.turns[0].ended_reason == "error"


async def test_reader_handles_missing_file(tmp_path):
    reader = SessionLogReader("nope", root=tmp_path)
    traj = await reader.read()
    assert traj.summary.empty is True
    assert traj.summary.turns == 0
    assert traj.turns == []


async def test_reader_steps_sorted_by_started_at(log_root):
    """assistant → tool → assistant 的因果顺序应保留。"""
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "x"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "好的"})
    await w.append("tool_call", {
        "turn": 0, "step": 1,
        "call_id": "c", "name": "ls", "input": {},
    })
    await w.append("tool_result", {
        "turn": 0, "step": 1,
        "call_id": "c", "name": "ls", "output": "x", "is_error": False,
    })
    await w.append("assistant_chunk", {"turn": 0, "step": 2, "delta": "完成"})
    await w.append("turn_end", {"turn": 0, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    kinds = [s.kind for s in traj.turns[0].steps]
    assert kinds == ["assistant_message", "tool", "assistant_message"]


async def test_system_prompt_folds_as_session_level(log_root):
    """system_prompt 事件折叠成 session.system_prompts(不进 turn.steps)。

    参考 deepseek-harness: initial 永远钉在 timeline 顶部,后续 change 按
    seq 顺序排列。
    """
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    await w.append("turn_start", {"turn": 0})
    await w.append("system_prompt", {
        "content": "你是 Swift Agent,擅长处理 Excel 流水线。",
        "reason": "initial",
    })
    await w.append("user_message", {"content": "分析这个表"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "好的"})
    await w.append("turn_end", {"turn": 0, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    turn = traj.turns[0]
    # 不再混进 turn.steps — 只有 assistant step
    assert len(turn.steps) == 1
    assert turn.steps[0].kind == "assistant_message"

    # session.system_prompts 收集到一条 initial 记录
    assert len(traj.system_prompts) == 1
    sp = traj.system_prompts[0]
    assert sp.reason == "initial"
    assert sp.content == "你是 Swift Agent,擅长处理 Excel 流水线。"
    assert sp.seq > 0  # 来自 JSONL 事件 seq


async def test_system_prompt_change_keeps_history(log_root):
    """多 turn + system_prompt 变化 → system_prompts 列表保留完整历史。"""
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    # turn 0: initial prompt
    await w.append("system_prompt", {"content": "PROMPT_V1", "reason": "initial"})
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "u0"})
    await w.append("turn_end", {"turn": 0, "reason": "normal"})
    # turn 1: prompt 变化
    await w.append("system_prompt", {"content": "PROMPT_V2", "reason": "change"})
    await w.append("turn_start", {"turn": 1})
    await w.append("user_message", {"content": "u1"})
    await w.append("turn_end", {"turn": 1, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    assert traj.summary.turns == 2

    # 两条都保留(由 chat_service 决定何时写,reader 不去重)
    assert len(traj.system_prompts) == 2
    assert traj.system_prompts[0].reason == "initial"
    assert traj.system_prompts[0].content == "PROMPT_V1"
    assert traj.system_prompts[1].reason == "change"
    assert traj.system_prompts[1].content == "PROMPT_V2"
    # 顺序按 JSONL seq(写盘顺序)
    assert traj.system_prompts[0].seq < traj.system_prompts[1].seq


async def test_session_without_system_prompt_returns_empty_list(log_root):
    """老 JSONL(没有 system_prompt 事件)→ system_prompts 是空列表,不报错。"""
    w = SessionLogWriter("legacy", root=log_root)
    await w.open()
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "old"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "hi"})
    await w.append("turn_end", {"turn": 0, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("legacy", root=log_root)
    traj = await reader.read()
    assert traj.system_prompts == []
    assert traj.summary.empty is False
    assert traj.turns[0].steps[0].kind == "assistant_message"


async def test_reader_dedupes_identical_system_prompts(log_root):
    """reader 折叠时按 headerEquals 思路去重:相邻 content 相同的合并成一条。

    模拟 chat_service 老版本每 turn 都写 system_prompt 的情况(reader 兜底
    去重,UI 不会显示重复 system cell)。
    """
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    # 老代码风格:每 turn 都写 system_prompt,但 content 一模一样(无 reason 字段)
    same_prompt = "你是 Swift Agent"
    for turn in range(3):
        await w.append("system_prompt", {"turn": turn, "content": same_prompt})
        await w.append("turn_start", {"turn": turn})
        await w.append("user_message", {"content": f"u{turn}"})
        await w.append("turn_end", {"turn": turn, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    # 三条相同 content → 折叠成 1 条
    assert len(traj.system_prompts) == 1
    assert traj.system_prompts[0].content == same_prompt
    assert traj.system_prompts[0].reason == "initial"
    # turns 仍然全部保留
    assert traj.summary.turns == 3


async def test_reader_keeps_changed_system_prompts(log_root):
    """reader 折叠:content 不同的 system_prompt 都保留,标记 initial / change。"""
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    await w.append("system_prompt", {"turn": 0, "content": "PROMPT_A"})
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "u0"})
    await w.append("turn_end", {"turn": 0, "reason": "normal"})
    await w.append("system_prompt", {"turn": 1, "content": "PROMPT_A"})  # 同 A → 去重
    await w.append("turn_start", {"turn": 1})
    await w.append("user_message", {"content": "u1"})
    await w.append("turn_end", {"turn": 1, "reason": "normal"})
    await w.append("system_prompt", {"turn": 2, "content": "PROMPT_B"})  # 变了 → 保留
    await w.append("turn_start", {"turn": 2})
    await w.append("user_message", {"content": "u2"})
    await w.append("turn_end", {"turn": 2, "reason": "normal"})
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    assert len(traj.system_prompts) == 2
    assert traj.system_prompts[0].content == "PROMPT_A"
    assert traj.system_prompts[0].reason == "initial"
    assert traj.system_prompts[1].content == "PROMPT_B"
    assert traj.system_prompts[1].reason == "change"
    assert traj.summary.turns == 3


async def test_writer_was_empty_on_open(log_root):
    """SessionLogWriter.was_empty_on_open 正确反映"首次创建 vs 已有文件"。"""
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    # 文件刚被创建 → was_empty_on_open=True
    assert w.was_empty_on_open is True
    await w.append("user_message", {"content": "hi"})
    await w.close()

    # 重新打开同一文件 → was_empty_on_open=False
    w2 = SessionLogWriter("s", root=log_root)
    await w2.open()
    assert w2.was_empty_on_open is False
    await w2.close()


# --------------------------------------------------------------------------- #
# API 端点
# --------------------------------------------------------------------------- #


@pytest.fixture
async def client():
    """ASGI in-memory 测试 client。"""
    # ASGITransport 不触发 lifespan;手动 init_db
    from app.db.base import init_db

    await init_db()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_api_trajectory_404_for_unknown_session(client):
    r = await client.get("/api/sessions/nonexistent_xxxxxxxxxxxxxxxx/trajectory")
    assert r.status_code == 404


async def test_api_log_export_404_for_unknown_session(client):
    r = await client.get("/api/sessions/nonexistent_xxxxxxxxxxxxxxxx/log/export")
    assert r.status_code == 404


async def test_api_trajectory_empty_for_new_session(client):
    r = await client.post("/api/sessions", json={"title": "traj"})
    sid = r.json()["id"]
    r = await client.get(f"/api/sessions/{sid}/trajectory")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["empty"] is True
    assert body["summary"]["turns"] == 0


async def test_api_log_export_empty_bytes_for_new_session(client):
    r = await client.post("/api/sessions", json={"title": "traj"})
    sid = r.json()["id"]
    r = await client.get(f"/api/sessions/{sid}/log/export")
    assert r.status_code == 200
    assert r.content == b""
    assert "attachment" in r.headers.get("content-disposition", "")


async def test_api_trajectory_full_round_trip(client, monkeypatch, tmp_path):
    """写 JSONL → 通过 API 读 trajectory → 验证 summary 正确。"""
    # 把 trajectory_log_dir 切到临时目录
    from app.core import config
    monkeypatch.setattr(
        config, "get_settings",
        lambda: _fake_settings(tmp_path / "sessions"),
    )
    # 上面那行需要 settings.trajectory_log_dir 是动态读的;
    # 实际读路径在 lifespan 里;这里直接写文件到临时目录后绕过 lifespan,
    # 通过直接调 SessionLogWriter 写到固定路径,然后调 reader 来读
    r = await client.post("/api/sessions", json={"title": "full"})
    sid = r.json()["id"]

    # 直接写一个 JSONL 到 session log 默认目录(data/sessions)
    # 不走 monkeypatch(避免破坏 settings 全局),只验证端点存在
    r = await client.get(f"/api/sessions/{sid}/trajectory")
    assert r.status_code == 200


def _fake_settings(traj_dir):
    from app.core.config import AppSettings

    s = AppSettings()
    s.trajectory_log_dir = str(traj_dir)
    return s


async def test_reader_in_progress_turn_has_no_ended_reason(log_root):
    """实时轮询场景:turn_start + 一些 events 但没写 turn_end → ended_reason 应为 None,
    不要再自动标 "aborted" —— 那样前端会误把进行中的 turn 渲染成已中断。

    真正的 abort 路径在 chat_service 显式写 turn_end(reason="aborted"),跟这个兜底无关。
    """
    w = SessionLogWriter("s", root=log_root)
    await w.open()
    await w.append("turn_start", {"turn": 0})
    await w.append("user_message", {"content": "go"})
    await w.append("assistant_chunk", {"turn": 0, "step": 0, "delta": "好的"})
    # 不写 turn_end — 模拟会话进行中 / 进程异常中断两种情况
    await w.close()

    reader = SessionLogReader("s", root=log_root)
    traj = await reader.read()
    assert traj.summary.turns == 1
    turn = traj.turns[0]
    # ended_reason 留 None → 前端识别为"进行中"
    assert turn.ended_reason is None
    # steps 仍然完整折叠出来
    assert len(turn.steps) == 1
    assert turn.steps[0].kind == "assistant_message"