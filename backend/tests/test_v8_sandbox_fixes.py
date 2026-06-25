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