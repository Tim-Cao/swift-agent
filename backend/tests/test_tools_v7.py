"""v7:Excel pipeline 4 个 tool 的行为测试。

覆盖:
- unzip_archive:正常解压 + 跳过 zip slip
- inspect_csv:读 CSV + 字段推断
- execute_pandas_code:happy path + sandbox 拒绝 import / open / dunder
- write_excel:生成 xlsx + 表头加粗 + 冻结首行
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from tools import TOOLKIT, get_tools
from tools import excel_pipeline as _excel_pipeline  # noqa: F401  触发 4 个 tool 注册

unzip_archive = TOOLKIT["unzip_archive"]
inspect_csv = TOOLKIT["inspect_csv"]
execute_pandas_code = TOOLKIT["execute_pandas_code"]
write_excel = TOOLKIT["write_excel"]


# --------------------------------------------------------------------------- #
# unzip_archive
# --------------------------------------------------------------------------- #


def _make_zip(files: dict[str, str]) -> bytes:
    """files: {filename: content} → 返回 zip 字节。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_unzip_archive_extracts_csvs(tmp_path):
    zip_path = tmp_path / "src.zip"
    zip_path.write_bytes(_make_zip({
        "a.csv": "id,name\n1,A\n",
        "sub/b.csv": "id,val\n1,10\n",
    }))
    out = unzip_archive.invoke({"zip_path": str(zip_path), "dest_dir": str(tmp_path / "out")})
    assert "error" not in out
    assert out["total_count"] == 2
    assert "a.csv" in out["csv_files"]
    assert any(f.endswith("b.csv") for f in out["csv_files"])
    assert (tmp_path / "out" / "a.csv").exists()
    assert (tmp_path / "out" / "sub" / "b.csv").exists()


def test_unzip_archive_skips_zip_slip(tmp_path):
    # 构造一个 zip slip 攻击:文件名 "../evil.csv"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("safe.csv", "ok\n")
        zf.writestr("../evil.csv", "evil\n")
    zip_path = tmp_path / "attack.zip"
    zip_path.write_bytes(buf.getvalue())

    out = unzip_archive.invoke({"zip_path": str(zip_path), "dest_dir": str(tmp_path / "out")})
    assert out["total_count"] == 1
    assert out["skipped_unsafe"]  # 至少一条被跳过
    # evil.csv 不应在 dest_dir 外被创建
    assert not (tmp_path / "evil.csv").exists()


def test_unzip_archive_missing_zip(tmp_path):
    out = unzip_archive.invoke({
        "zip_path": str(tmp_path / "nope.zip"),
        "dest_dir": str(tmp_path / "out"),
    })
    assert "error" in out


# --------------------------------------------------------------------------- #
# inspect_csv
# --------------------------------------------------------------------------- #


def test_inspect_csv_basic(tmp_path):
    csv_path = tmp_path / "x.csv"
    df = pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "A"], "price": [10.5, 20.0, 30.25]})
    df.to_csv(csv_path, index=False)
    out = inspect_csv.invoke({"csv_path": str(csv_path), "sample_rows": 3})
    assert "error" not in out
    assert out["row_count"] == 3
    assert out["column_count"] == 3
    col_names = {c["name"] for c in out["columns"]}
    assert col_names == {"id", "name", "price"}
    types = {c["name"]: c["dtype"] for c in out["columns"]}
    assert types["id"] == "integer"
    assert types["price"] == "float"
    assert types["name"] == "string"
    assert len(out["sample"]) == 3


def test_inspect_csv_missing(tmp_path):
    out = inspect_csv.invoke({"csv_path": str(tmp_path / "nope.csv")})
    assert "error" in out


# --------------------------------------------------------------------------- #
# execute_pandas_code
# --------------------------------------------------------------------------- #


@pytest.fixture
def csv_dir(tmp_path):
    d = tmp_path / "csv"
    d.mkdir()
    pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "A"]}).to_csv(d / "a.csv", index=False)
    pd.DataFrame({"id": [1, 2], "region": ["east", "west"]}).to_csv(d / "b.csv", index=False)
    return d


def test_execute_pandas_code_dedup_and_merge(csv_dir, tmp_path):
    code = (
        "duplicated = a[a.duplicated(subset=['name'], keep=False)]\n"
        "RESULT_DF = duplicated.merge(b, on='id', how='left')\n"
    )
    out_csv = tmp_path / "result.csv"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv", "b.csv"],
        "output_csv": str(out_csv),
    })
    assert out["ok"] is True
    assert out["result_csv"] is not None
    assert Path(out["result_csv"]).exists()
    assert out["result_summary"]["row_count"] == 2  # A 出现 2 次
    assert set(out["result_summary"]["columns"]) == {"id", "name", "region"}


def test_execute_pandas_code_no_result_df(csv_dir):
    code = "x = 1\n"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is False
    assert "RESULT_DF" in out["error"]


def test_execute_pandas_code_sandbox_rejects_import(csv_dir):
    code = "import os\nRESULT_DF = a\n"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is False
    assert "Import not allowed" in out["error"]


def test_execute_pandas_code_sandbox_rejects_open(csv_dir):
    code = "RESULT_DF = open('a.csv')\n"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is False
    assert "Call not allowed" in out["error"]


def test_execute_pandas_code_sandbox_rejects_dunder(csv_dir):
    code = "RESULT_DF = a.__class__\n"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is False
    assert "Dunder" in out["error"]


# --------------------------------------------------------------------------- #
# write_excel
# --------------------------------------------------------------------------- #


def test_write_excel_creates_file_with_styling(tmp_path):
    src = tmp_path / "data.csv"
    pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "C"], "amount": [100, 200, 300]}).to_csv(src, index=False)
    out_xlsx = tmp_path / "out.xlsx"

    out = write_excel.invoke({
        "csv_path": str(src),
        "output_path": str(out_xlsx),
        "sheet_name": "Result",
    })
    assert "error" not in out
    assert out["output_path"].endswith("out.xlsx")
    assert out["row_count"] == 3
    assert out["size_bytes"] > 0
    assert out_xlsx.exists()

    # 用 openpyxl 验样式:表头加粗 + 冻结首行
    wb = load_workbook(out_xlsx)
    ws = wb["Result"]
    assert ws.cell(row=1, column=1).font.bold is True
    assert ws.freeze_panes == "A2"


def test_write_excel_missing_csv(tmp_path):
    out = write_excel.invoke({
        "csv_path": str(tmp_path / "nope.csv"),
        "output_path": str(tmp_path / "out.xlsx"),
    })
    assert "error" in out