"""subagents/__init__.py 行为测试。

v7 注:ALL_SUBAGENTS 已被 v7 在 import 时填入 4 个 subagent,
不能再假设它为空。test_append_works 只 append/pop,不再 clear()
以免污染其它测试模块的全局视图。
"""

from __future__ import annotations

from subagents import ALL_SUBAGENTS


def test_default_not_empty_after_v7():
    """v7 起 ALL_SUBAGENTS 至少含 4 个 v7 注册的 subagent。"""
    names = {a["name"] for a in ALL_SUBAGENTS}
    assert {"IntakeAgent", "RuleParserAgent",
            "DataProcessingAgent", "ExcelWriterAgent"} <= names


def test_append_works():
    agent = {"name": "_TEST_TMP", "description": "d", "system_prompt": "s"}
    before = len(ALL_SUBAGENTS)
    ALL_SUBAGENTS.append(agent)
    try:
        assert ALL_SUBAGENTS[-1] is agent
        assert len(ALL_SUBAGENTS) == before + 1
    finally:
        ALL_SUBAGENTS.remove(agent)
