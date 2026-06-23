"""v8:chat_service 的 file 事件检测。

覆盖:
- _detect_file_event 识别 .xlsx 路径
- 同时支持 /tmp/swift-agent 和 /private/tmp/swift-agent(macOS symlink)
- url 拼成 /api/downloads/<sid>/<filename>
- 不存在的路径返回 None(不误发)
- 命中后 size_bytes 等于文件实际大小
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.services.chat_service import _detect_file_event

# 真实根目录(必须放在 /tmp/swift-agent/<sid>/ 下,正则才能匹配)
UPLOAD_ROOT = Path("/tmp/swift-agent")
SID = "9dba63da92e24f6cb55650a79cbe49f5"


@pytest.fixture
def session_dir():
    """在 /tmp/swift-agent/<SID> 下临时建一个 session 目录,测试完清理。"""
    d = UPLOAD_ROOT / SID
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_detect_xlsx_under_tmp(session_dir):
    """正常 /tmp 路径。"""
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"fake-xlsx-content")
    text = f"Excel 已生成: {xlsx}  共 100 行"
    evt = _detect_file_event(text, SID)
    assert evt is not None
    assert evt["event"] == "file"
    assert evt["data"]["url"] == f"/api/downloads/{SID}/result.xlsx"
    assert evt["data"]["filename"] == "result.xlsx"
    assert evt["data"]["mime"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert evt["data"]["size_bytes"] == len(b"fake-xlsx-content")


def test_detect_xlsx_under_private_tmp(session_dir):
    """macOS /tmp 是 symlink → /private/tmp,LLM 写出来的 resolved 路径
    也必须能匹配(否则 file 事件不发出,前端收不到下载链接)。"""
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"x")
    # 强制构造 /private/tmp 前缀的字符串(模拟 macOS resolved 路径)
    private_form = str(xlsx).replace("/tmp/", "/private/tmp/", 1)
    text = f"saved to {private_form} done"
    evt = _detect_file_event(text, SID)
    assert evt is not None
    assert evt["data"]["url"] == f"/api/downloads/{SID}/result.xlsx"


def test_detect_xlsx_filename_extracted(session_dir):
    """xlsx 在子目录下也能正确提取文件名(只取 basename 给前端)。"""
    sub = session_dir / "csv"
    sub.mkdir()
    xlsx = sub / "result.xlsx"
    xlsx.write_bytes(b"x")
    text = f"saved {xlsx} ok"
    evt = _detect_file_event(text, SID)
    assert evt is not None
    assert evt["data"]["filename"] == "result.xlsx"
    # url 里的 filename 部分也是 basename
    assert evt["data"]["url"].endswith("/result.xlsx")


def test_detect_xlsx_missing_path_returns_none():
    """xlsx 路径在文本里但实际文件不存在 → 不发 file 事件。"""
    text = f"output: /tmp/swift-agent/{SID}/nope.xlsx done"
    evt = _detect_file_event(text, SID)
    assert evt is None


def test_detect_xlsx_no_xlsx_in_text():
    text = "没有附件"
    evt = _detect_file_event(text, SID)
    assert evt is None


def test_detect_xlsx_none_output():
    """None 输入也不崩。"""
    assert _detect_file_event(None, SID) is None
    assert _detect_file_event("", SID) is None
