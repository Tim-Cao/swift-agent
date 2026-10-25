"""Excel 流水线 agent 的种子配置测试。

v11:Excel 流水线不再是 Python 子 Agent(``subagents/`` 目录已删),
而是 5 条普通 DB 记录(1 supervisor + 4 子 agent),配置放在
``app/db/seed_data/excel_pipeline.py`` 里,启动时播种进 agents 表。

这些测试锁住种子数据的结构与关键提示词约束。
"""

from __future__ import annotations

from app.db.seed_data.excel_pipeline import CHILDREN, SUPERVISOR

EXPECTED_CHILD_NAMES = {
    "IntakeAgent",
    "RuleParserAgent",
    "DataProcessingAgent",
    "ExcelWriterAgent",
}


def _by_name(name: str) -> dict:
    for c in CHILDREN:
        if c["name"] == name:
            return c
    raise AssertionError(f"agent {name} not in seed data")


def test_supervisor_exists_and_is_default():
    assert SUPERVISOR["name"] == "Supervisor"
    assert SUPERVISOR["is_default"] is True
    assert SUPERVISOR["system_prompt"]


def test_four_children_present():
    assert {c["name"] for c in CHILDREN} == EXPECTED_CHILD_NAMES


def test_each_child_has_required_fields():
    required = {"name", "parent_name", "system_prompt", "tool_names"}
    for c in CHILDREN:
        missing = required - c.keys()
        assert not missing, f"{c.get('name')} missing {missing}"
        assert c["system_prompt"]
        assert c["parent_name"] == SUPERVISOR["name"]


def test_intake_agent_uses_unzip_and_inspect():
    intake = _by_name("IntakeAgent")
    assert set(intake["tool_names"]) == {"unzip_archive", "inspect_csv"}


def test_rule_parser_agent_uses_execute_pandas():
    rp = _by_name("RuleParserAgent")
    assert rp["tool_names"] == ["execute_pandas_code"]
    # system_prompt 必须明确提到 RESULT_DF 这个强制变量名
    assert "RESULT_DF" in rp["system_prompt"]


def test_data_processing_agent_uses_execute_pandas():
    dp = _by_name("DataProcessingAgent")
    assert dp["tool_names"] == ["execute_pandas_code"]


def test_excel_writer_agent_uses_write_excel():
    ew = _by_name("ExcelWriterAgent")
    assert ew["tool_names"] == ["write_excel"]


def test_descriptions_folded_into_prompt_first_line():
    """DB 里没有 description 字段 —— 原来的 description 被折进提示词首行。

    运行时取首行当 deepagents subagent 的 description,父 agent 靠它
    决定何时委派,所以首行必须是"这个 agent 干什么"的说明。
    """
    for c in CHILDREN:
        first = c["system_prompt"].splitlines()[0].strip()
        assert first, f"{c['name']} 首行为空"
        assert len(first) > 10
