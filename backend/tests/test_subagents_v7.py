"""v7:Excel pipeline 4 个 subagent 的提示词约束(改为读种子数据)。

v11:``subagents/`` 目录已删,4 个子 agent 变成 DB 记录,提示词文本放在
``app/db/seed_data/excel_pipeline.py``。本文件锁住各子 agent 的工具绑定
与关键提示词约束(原先在 subagents/*.py 里,现在在种子数据里)。
"""

from __future__ import annotations

from app.db.seed_data.excel_pipeline import CHILDREN, SUPERVISOR

EXPECTED_NAMES = {
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


def test_all_subagents_count():
    assert len(CHILDREN) == 4


def test_all_subagents_names():
    assert {c["name"] for c in CHILDREN} == EXPECTED_NAMES


def test_intake_agent_uses_unzip_and_inspect():
    intake = _by_name("IntakeAgent")
    assert "unzip_archive" in intake["tool_names"]
    assert "inspect_csv" in intake["tool_names"]
    # 首行(原 description)必须提到 zip / csv 之类关键词
    desc = intake["system_prompt"].splitlines()[0]
    assert "zip" in desc.lower()
    assert "csv" in desc.lower()


def test_rule_parser_agent_uses_execute_pandas():
    rp = _by_name("RuleParserAgent")
    assert "execute_pandas_code" in rp["tool_names"]
    # system_prompt 必须明确提到 RESULT_DF 这个强制变量名
    assert "RESULT_DF" in rp["system_prompt"]


def test_data_processing_agent_uses_execute_pandas():
    dp = _by_name("DataProcessingAgent")
    assert "execute_pandas_code" in dp["tool_names"]


def test_excel_writer_agent_uses_write_excel():
    ew = _by_name("ExcelWriterAgent")
    assert "write_excel" in ew["tool_names"]


def test_supervisor_prompt_mentions_subagents():
    """supervisor 提示词里要写明 4 个子 agent 的名字(否则父 agent 不知道能委派给谁)。"""
    sp = SUPERVISOR["system_prompt"]
    for short in ("IntakeAgent", "RuleParserAgent",
                  "DataProcessingAgent", "ExcelWriterAgent"):
        assert short in sp
