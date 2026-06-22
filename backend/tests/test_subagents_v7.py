"""v7:Excel pipeline 4 个 subagent 注册 + 字段验证。

subagent 注册依赖:
  subagents/__init__.py 在 import 时会触发 tools.excel_pipeline 注册,
  然后导入 4 个 subagent 模块。每个 subagent 用 get_tools([...]) 在模块顶层
  拉取工具,所以本测试文件只需 import 即可。
"""

from __future__ import annotations

from subagents import ALL_SUBAGENTS


EXPECTED_NAMES = {
    "IntakeAgent",
    "RuleParserAgent",
    "DataProcessingAgent",
    "ExcelWriterAgent",
}


def test_all_subagents_count():
    assert len(ALL_SUBAGENTS) == 4


def test_all_subagents_names():
    names = {a["name"] for a in ALL_SUBAGENTS}
    assert names == EXPECTED_NAMES


def test_each_agent_has_required_fields():
    required = {"name", "description", "system_prompt"}
    for agent in ALL_SUBAGENTS:
        missing = required - agent.keys()
        assert not missing, f"{agent.get('name')} missing {missing}"
        assert agent["name"]
        assert agent["description"]
        assert agent["system_prompt"]


def test_intake_agent_uses_unzip_and_inspect():
    intake = next(a for a in ALL_SUBAGENTS if a["name"] == "IntakeAgent")
    tool_names = [getattr(t, "name", None) for t in intake["tools"]]
    assert "unzip_archive" in tool_names
    assert "inspect_csv" in tool_names
    # description 必须提到 zip / csv 之类关键词
    assert "zip" in intake["description"].lower()
    assert "csv" in intake["description"].lower()


def test_rule_parser_agent_uses_execute_pandas():
    rp = next(a for a in ALL_SUBAGENTS if a["name"] == "RuleParserAgent")
    tool_names = [getattr(t, "name", None) for t in rp["tools"]]
    assert "execute_pandas_code" in tool_names
    # system_prompt 必须明确提到 RESULT_DF 这个强制变量名
    assert "RESULT_DF" in rp["system_prompt"]


def test_data_processing_agent_uses_execute_pandas():
    dp = next(a for a in ALL_SUBAGENTS if a["name"] == "DataProcessingAgent")
    tool_names = [getattr(t, "name", None) for t in dp["tools"]]
    assert "execute_pandas_code" in tool_names


def test_excel_writer_agent_uses_write_excel():
    ew = next(a for a in ALL_SUBAGENTS if a["name"] == "ExcelWriterAgent")
    tool_names = [getattr(t, "name", None) for t in ew["tools"]]
    assert "write_excel" in tool_names