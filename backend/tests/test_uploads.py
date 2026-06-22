"""v7:/api/uploads POST 端点测试。

用 TestClient + tmp zip + 实际 /tmp/swift-agent/ 写入来验:
- 返回结构(session_id / upload_dir / csv_files / size_bytes / skipped_unsafe)
- 解压后文件确实落盘
- zip slip 攻击被跳过
- 不带 session_id 时后端自动创建
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app


def _make_zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def client():
    # uploads.py 直接写 /tmp/swift-agent/,需确认目录可写;CI 通常 OK
    os.makedirs("/tmp/swift-agent", exist_ok=True)
    with TestClient(app) as c:
        yield c


def test_upload_zip_basic(client):
    zip_bytes = _make_zip_bytes({
        "a.csv": "id,name\n1,A\n2,B\n",
        "b.csv": "id,val\n1,10\n",
    })
    resp = client.post(
        "/api/uploads",
        files={"file": ("test.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "session_id" in data
    assert len(data["session_id"]) == 32
    # macOS 上 /tmp 是 /private/tmp 的 symlink,用 resolve() 比对
    assert Path(data["upload_dir"]).resolve().parent.parent == Path("/tmp/swift-agent").resolve()
    assert sorted(data["csv_files"]) == ["a.csv", "b.csv"]
    assert data["size_bytes"] == len(zip_bytes)
    assert data["skipped_unsafe"] == []
    # 文件确实落盘
    upload_dir = Path(data["upload_dir"])
    assert (upload_dir / "a.csv").exists()
    assert (upload_dir / "b.csv").exists()


def test_upload_zip_with_session_id(client):
    zip_bytes = _make_zip_bytes({"x.csv": "a,b\n1,2\n"})
    sid = "abcdef0123456789abcdef0123456789"  # 32 hex
    resp = client.post(
        "/api/uploads",
        files={"file": ("t.zip", zip_bytes, "application/zip")},
        data={"session_id": sid},
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid
    assert Path(resp.json()["upload_dir"]).resolve().name == "csv"
    assert Path(resp.json()["upload_dir"]).resolve().parent.name == sid


def test_upload_zip_skips_zip_slip(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ok.csv", "x\n1\n")
        zf.writestr("../evil.csv", "evil\n")
    zip_bytes = buf.getvalue()
    resp = client.post(
        "/api/uploads",
        files={"file": ("attack.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["csv_files"] == ["ok.csv"]
    assert any("evil" in s for s in data["skipped_unsafe"])


def test_upload_invalid_zip(client):
    resp = client.post(
        "/api/uploads",
        files={"file": ("bad.zip", b"not a real zip", "application/zip")},
    )
    assert resp.status_code == 400
    assert "zip" in resp.json()["detail"].lower()