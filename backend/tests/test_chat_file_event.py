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


def test_detect_xlsx_in_accumulated_text_token_by_token(session_dir):
    """v8.6:stream_chat 在每个 token 到达时扫描累积文本。
    模拟 LLM 边输出边暴露 xlsx 路径:前 N 个 token 还没出现路径 → None,
    出现路径的 token 之后立刻返回 file 事件(只发一次——靠 stream_chat
    自己的 file_emitted 标志去重,_detect_file_event 本身每次都返回)。"""
    xlsx = session_dir / "result.xlsx"
    xlsx.write_bytes(b"x")
    path = str(xlsx)

    # 模拟 stream_chat 的扫描循环:_detect_file_event 每次都返回,
    # stream_chat 自己的 file_emitted 标志保证 file 事件只发一次
    accumulated = ""
    file_emitted = False
    first_file_evt = None
    emit_count = 0
    for tok in ["Done. ", "Saved to ", path, " — 100 rows."]:
        accumulated += tok
        evt = _detect_file_event(accumulated, SID)
        if evt and not file_emitted:
            file_emitted = True
            first_file_evt = evt
            emit_count += 1
        elif evt and file_emitted:
            # 模拟 stream_chat 不再 yield
            pass

    assert first_file_evt is not None
    assert first_file_evt["data"]["filename"] == "result.xlsx"
    assert emit_count == 1  # 整个流期间 file 事件只发 1 次
