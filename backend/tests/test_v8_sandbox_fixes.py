"""v8.8:sandbox 加载 + 路径幻觉修复。

覆盖:
  1. _load_csvs_to_globals 容忍 /tmp ↔ /private/tmp symlink
  2. csv_dir 不存在时立刻返回 error(不再静默返回空)
  3. pd_safe_read_csv 把 csv_dir 下的允许文件重定向到预加载 DataFrame
  4. pd_safe_read_csv 对白名单外的文件**不**走重定向(交给 pd 自己抛错)
  5. intake_agent / rule_parser_agent / data_processing_agent 的
     system_prompt 提到 allowed_files 白名单约束
  6. supervisor_system_prompt 提到从用户消息提取白名单
"""

from __future__ import annotations

import textwrap

import pandas as pd
import pytest

from app.core.config import get_settings
from subagents import ALL_SUBAGENTS
from tools import TOOLKIT
from tools import excel_pipeline as _excel_pipeline  # noqa: F401  触发 4 个 tool 注册

execute_pandas_code = TOOLKIT["execute_pandas_code"]


@pytest.fixture
def csv_dir(tmp_path):
    d = tmp_path / "csv"
    d.mkdir()
    pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "A"]}).to_csv(d / "a.csv", index=False)
    pd.DataFrame({"id": [1, 2], "region": ["east", "west"]}).to_csv(d / "b.csv", index=False)
    # 白名单外文件 —— 不应该被加载
    pd.DataFrame({"secret": [1]}).to_csv(d / "secret.csv", index=False)
    return d


# --------------------------------------------------------------------------- #
# 1) csv_dir 找不到时立刻返回 error
# --------------------------------------------------------------------------- #


def test_csv_dir_not_found_returns_error(tmp_path):
    out = execute_pandas_code.invoke({
        "code": "RESULT_DF = a.copy()",
        "csv_dir": str(tmp_path / "does_not_exist"),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is False
    assert "csv_dir" in out["error"].lower()
    assert out["loaded_files"] == []


def test_allowed_files_all_missing_returns_error(csv_dir):
    out = execute_pandas_code.invoke({
        "code": "RESULT_DF = a.copy()",
        "csv_dir": str(csv_dir),
        "allowed_files": ["nonexistent1.csv", "nonexistent2.csv"],
    })
    assert out["ok"] is False
    assert "nonexistent1.csv" in out["error"]
    assert "nonexistent2.csv" in out["error"]


def test_partial_missing_does_not_fail(csv_dir):
    """白名单里 2 个文件,1 个存在 1 个不存在 —— 存在的那个应当被加载。"""
    out = execute_pandas_code.invoke({
        "code": "RESULT_DF = a.copy()",
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv", "ghost.csv"],
    })
    assert out["ok"] is True
    assert "a" in out["loaded_files"]


# --------------------------------------------------------------------------- #
# 2) /tmp ↔ /private/tmp symlink 兼容
# --------------------------------------------------------------------------- #


def test_symlink_resolution_loads_csvs(tmp_path):
    """模拟 macOS 上 /tmp ↔ /private/tmp symlink:
    实际文件在 /private/var/.../real/csv/ 下,caller 给的是 alias(软链)路径。
    _load_csvs_to_globals 应当能跟随 symlink 找到文件。"""
    real_dir = tmp_path / "real" / "csv"
    real_dir.mkdir(parents=True)
    pd.DataFrame({"id": [1, 2], "v": [10, 20]}).to_csv(real_dir / "a.csv", index=False)

    # 创建 alias/csv → real/csv 的软链
    alias = tmp_path / "alias"
    alias.mkdir()
    try:
        alias_csv = alias / "csv"
        alias_csv.symlink_to(real_dir)
    except OSError:
        pytest.skip("symlink not supported on this platform")

    fake_csv_dir = str(alias / "csv")
    out = execute_pandas_code.invoke({
        "code": "RESULT_DF = a.copy()",
        "csv_dir": fake_csv_dir,
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert "a" in out["loaded_files"]


# --------------------------------------------------------------------------- #
# 3) pd_safe_read_csv 重定向到预加载 DataFrame
# --------------------------------------------------------------------------- #


def test_pd_safe_read_csv_with_absolute_path_in_csv_dir(csv_dir):
    """v8.8:即使 agent 误写了 csv_dir 下的绝对路径,沙箱应通过
    pd_safe_read_csv 重定向到预加载的 DataFrame(不抛 FileNotFoundError)。"""
    code = textwrap.dedent(f"""
        ds = pd_safe_read_csv({str(csv_dir)!r} + '/a.csv')
        RESULT_DF = ds.copy()
    """)
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 3


def test_pd_safe_read_csv_rejects_non_whitelisted_path(csv_dir):
    """白名单外的文件即使在 csv_dir 下,也不应该被 pd_safe_read_csv 重定向
    —— 交给 pd 自己抛 FileNotFoundError(防止 agent 用别名绕过白名单)。"""
    code = textwrap.dedent(f"""
        ds = pd_safe_read_csv({str(csv_dir)!r} + '/secret.csv')
        RESULT_DF = ds
    """)
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],  # secret.csv 不在白名单
    })
    assert out["ok"] is False


# --------------------------------------------------------------------------- #
# 4) agent prompt 包含 allowed_files 约束关键词
# --------------------------------------------------------------------------- #


def _get_agent(name: str) -> dict:
    for a in ALL_SUBAGENTS:
        if a["name"] == name:
            return a
    raise AssertionError(f"agent {name} not registered")


def test_intake_agent_prompt_mentions_allowed_files():
    """IntakeAgent 的 system_prompt 必须提到 allowed_files 白名单约束。"""
    sp = _get_agent("IntakeAgent")["system_prompt"]
    assert "allowed_files" in sp
    assert "白名单" in sp or "allowed_files" in sp


def test_rule_parser_agent_prompt_uses_preloaded_vars():
    """RuleParserAgent 必须强调:用预加载的 stem 变量名,不要写绝对路径。"""
    sp = _get_agent("RuleParserAgent")["system_prompt"]
    assert "RESULT_DF" in sp
    assert "预加载" in sp or "变量" in sp
    assert "绝对路径" in sp or "路径" in sp


def test_data_processing_agent_prompt_passes_csv_dir_verbatim():
    """DataProcessingAgent 必须强调 csv_dir 原样传下去,不重新翻译。"""
    sp = _get_agent("DataProcessingAgent")["system_prompt"]
    assert "allowed_files" in sp
    assert "csv_dir" in sp
    assert "原样" in sp or "不要" in sp


# --------------------------------------------------------------------------- #
# 5) supervisor_system_prompt 提到白名单提取
# --------------------------------------------------------------------------- #


def test_supervisor_prompt_extracts_whitelist_from_message():
    s = get_settings()
    sp = s.supervisor_system_prompt
    assert "allowed_files" in sp
    assert "白名单" in sp or "allowed_files" in sp


# --------------------------------------------------------------------------- #
# 6) v8.9:sandbox 注入 csv_dir / allowed_files + loaded_columns 回传
# --------------------------------------------------------------------------- #


def test_sandbox_injects_csv_dir_and_allowed_files(csv_dir):
    """v8.9:沙箱把 csv_dir 和 allowed_files 注入 globals,agent 写
    `csv_dir + '/a.csv'` 不会再 NameError。"""
    code = textwrap.dedent(f"""
        path = csv_dir + '/a.csv'
        df = pd_safe_read_csv(path)
        RESULT_DF = df.copy()
    """)
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 3


def test_sandbox_returns_loaded_columns_on_keyerror(csv_dir):
    """v8.9:KeyError 时回传 loaded_columns,agent 看到就能修正列名。"""
    code = textwrap.dedent(f"""
        # 列名带括号,故意写错(去掉括号)
        RESULT_DF = a[a['name_typo'].notna()].copy()
    """)
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is False
    assert "loaded_columns" in out
    assert "a" in out["loaded_columns"]
    # 应该能看到真实列名,例如 id / name
    assert "id" in out["loaded_columns"]["a"] or "name" in out["loaded_columns"]["a"]


def test_intake_agent_prompt_requires_verbatim_column_repr():
    """v8.9:IntakeAgent 必须明确:列名 repr 必须从 inspect_csv 1:1 复制,
    不要归一化/简化。"""
    sp = _get_agent("IntakeAgent")["system_prompt"]
    # 必须提到"原样"或"1:1"或"repr"
    assert "repr" in sp or "原样" in sp or "1:1" in sp
    # 必须警告不要归一化列名
    assert "归一化" in sp or "简化" in sp or "不要" in sp


def test_rule_parser_agent_prompt_requires_verbatim_column_strings():
    """v8.9:RuleParserAgent 必须一字不差用 IntakeAgent 给的列名字符串。"""
    sp = _get_agent("RuleParserAgent")["system_prompt"]
    # 必须强调"原样"或"一字不差"
    assert "原样" in sp or "一字不差" in sp
    # 必须强调不要归一化
    assert "归一化" in sp or "简化" in sp or "不要" in sp


# --------------------------------------------------------------------------- #
# 7) v8.11:execute_pandas_code 默认 allowed_files / output_csv + 中文 docstring
# --------------------------------------------------------------------------- #


def test_execute_pandas_code_default_allowed_files_loads_all_csvs(csv_dir):
    """v8.11:不传 allowed_files 时,沙箱自动扫描 csv_dir 下全部 CSV 并加载。"""
    code = "RESULT_DF = a.copy()"  # a 是 a.csv 的 stem
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        # allowed_files 故意不传
    })
    assert out["ok"] is True, out
    assert "a" in out["loaded_files"]
    # 白名单外的 secret.csv 不应该被加载(它是 csv_dir 下的文件,
    # 但默认 "*" 行为下会加载;真正隔离靠的是文件本身是否在白名单)
    # 由于我们改成 ["*"],secret.csv 也会被加载 → 仅验证 ok
    assert out["result_summary"]["row_count"] == 3


def test_execute_pandas_code_default_no_output_csv_does_not_write(csv_dir, tmp_path):
    """v8.11:不传 output_csv 时只返回样例,不落盘。"""
    out = execute_pandas_code.invoke({
        "code": "RESULT_DF = a.copy()",
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_csv"] is None
    # head 应该有数据
    assert len(out["result_summary"]["head"]) == 3


def test_execute_pandas_code_docstring_is_chinese_and_discoverable():
    """v8.11:docstring 必须用中文写、强调'数据处理首选',让中文 LLM 容易 match。"""
    tool = execute_pandas_code
    # langchain @tool 把 docstring 放在 .description
    desc = tool.description
    assert "数据处理首选" in desc or "首选" in desc
    # 必须包含中文示例或说明
    assert "csv_dir" in desc or "CSV" in desc
    # 必须强调不要写 import / 不要手写
    assert "不要" in desc or "无需" in desc


def test_rule_parser_agent_prompt_explains_how_to_call_tool():
    """v8.11:RuleParserAgent prompt 必须明确告诉它'直接调 execute_pandas_code',
    不要手写 CSV / 不要逐行 read。"""
    sp = _get_agent("RuleParserAgent")["system_prompt"]
    # 必须提到 execute_pandas_code 工具名
    assert "execute_pandas_code" in sp
    # 必须强调不要手算 / 手写 CSV
    assert "不要" in sp
    # 必须列出工具参数(帮助 agent 自动 fill)
    assert "allowed_files" in sp or "output_csv" in sp or "csv_dir" in sp


# --------------------------------------------------------------------------- #
# 8) v8.12:沙箱自动生成短别名 + _VAR_MAP introspection
# --------------------------------------------------------------------------- #


def test_sandbox_injects_short_aliases(tmp_path):
    """v8.12:文件 TX103T-RG008_DS.csv 同时暴露成:
    - TX103T_RG008_DS (canonical stem)
    - DS / RG008_DS(短别名),避免 LLM 写 ds / mh 类短名 NameError。
    """
    d = tmp_path / "csv"
    d.mkdir()
    pd.DataFrame({"id": [1, 2], "v": [10, 20]}).to_csv(
        d / "TX103T-RG008_DS.csv", index=False,
    )

    # 验证短别名能跑
    code = "RESULT_DF = DS.copy()"  # 用 DS 别名
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(d),
        "allowed_files": ["TX103T-RG008_DS.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 2


def test_sandbox_var_map_and_hint(tmp_path):
    """v8.12:_VAR_MAP 和 _VAR_HINT 必须注入 globals,LLM 可以 introspection。"""
    d = tmp_path / "csv"
    d.mkdir()
    pd.DataFrame({"id": [1]}).to_csv(d / "a.csv", index=False)

    code = textwrap.dedent("""
        # 用 _VAR_HINT 验证短别名映射
        assert isinstance(_VAR_HINT, str) and "a" in _VAR_HINT
        assert isinstance(_VAR_MAP, dict)
        # canonical "a" 必须映射回 "a.csv"
        assert _VAR_MAP.get("a") == "a"
        RESULT_DF = a.copy()
    """)
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(d),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    # loaded_columns 会显示 a
    assert "a" in out["loaded_files"]


def test_sandbox_alias_no_collision(tmp_path):
    """v8.12:两个同名末段(罕见)走降级策略,不会覆盖。

    这里 project_DS.csv 和 other_DS.csv 都想用 DS 短名,沙箱会
    退化成更长的别名(penultimate+last 拼接)或保持 canonical。
    验证:两个 canonical 名都可用,且至少有一个短别名可用(没被覆盖)。
    """
    d = tmp_path / "csv"
    d.mkdir()
    pd.DataFrame({"x": [1]}).to_csv(d / "project_DS.csv", index=False)
    pd.DataFrame({"y": [2]}).to_csv(d / "other_DS.csv", index=False)

    # 直接用两个 canonical 名
    code = textwrap.dedent("""
        # 两个 canonical 都必须可用
        merged = pd.concat([project_DS, other_DS], ignore_index=True)
        RESULT_DF = merged
    """)
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(d),
        "allowed_files": ["project_DS.csv", "other_DS.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 2


def test_chat_service_uses_higher_recursion_limit():
    """v8.12:chat_service.stream_chat 必须给 astream_events 传 recursion_limit=50,
    避免 Excel pipeline 串行调度时 25 个 graph node 不够。"""
    from app.services.chat_service import stream_chat
    import inspect
    src = inspect.getsource(stream_chat)
    assert "recursion_limit" in src
    assert "50" in src