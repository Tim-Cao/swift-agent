"""v7:Excel pipeline 端到端测试(不依赖真实 LLM)。

模拟完整流水线:
  1) 构造测试 zip(含 a.csv / b.csv)
  2) unzip_archive → 拿到 csv_files
  3) inspect_csv → 拿字段结构
  4) execute_pandas_code → 跑查重 + merge → 写 result.csv
  5) write_excel → 写 result.xlsx + 加样式

断言:
- 5 步全部 ok
- result.xlsx 落盘且非空
- result.xlsx 用 openpyxl 打开,数据行 = 预期值
- 表头加粗 / 冻结首行 / 列宽设置生效
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from tools import TOOLKIT
from tools import excel_pipeline as _excel_pipeline  # noqa: F401  触发注册

unzip_archive = TOOLKIT["unzip_archive"]
inspect_csv = TOOLKIT["inspect_csv"]
execute_pandas_code = TOOLKIT["execute_pandas_code"]
write_excel = TOOLKIT["write_excel"]


def _make_zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_full_pipeline_happy_path(tmp_path):
    # ---------- 1. 构造测试 zip ----------
    zip_bytes = _make_zip_bytes({
        "a.csv": "id,name,price\n1,A,10\n2,B,20\n3,A,30\n",
        "b.csv": "id,region\n1,east\n2,west\n3,east\n",
    })
    zip_path = tmp_path / "src.zip"
    zip_path.write_bytes(zip_bytes)

    # ---------- 2. unzip ----------
    work_dir = tmp_path / "work"
    unzip_out = unzip_archive.invoke({
        "zip_path": str(zip_path),
        "dest_dir": str(work_dir),
    })
    assert unzip_out["total_count"] == 2
    assert unzip_out["skipped_unsafe"] == []

    csv_dir = Path(unzip_out["dest_dir"])
    csv_files = sorted(unzip_out["csv_files"])
    assert csv_files == ["a.csv", "b.csv"]

    # ---------- 3. inspect ----------
    for fname in csv_files:
        info = inspect_csv.invoke({"csv_path": str(csv_dir / fname)})
        assert "error" not in info
        assert info["row_count"] >= 1
        assert info["column_count"] >= 1
        # 至少有一列 dtype 被推断出来
        types = {c["dtype"] for c in info["columns"]}
        assert "integer" in types or "string" in types

    # ---------- 4. 跑 pandas 代码:查重 name + merge region ----------
    code = (
        "duplicated = a[a.duplicated(subset=['name'], keep=False)]\n"
        "RESULT_DF = duplicated.merge(b, on='id', how='left')\n"
        "RESULT_DF = RESULT_DF.sort_values('id').reset_index(drop=True)\n"
    )
    result_csv = tmp_path / "result.csv"
    pd_out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": csv_files,
        "output_csv": str(result_csv),
    })
    assert pd_out["ok"] is True, pd_out
    assert result_csv.exists()
    assert pd_out["result_summary"]["row_count"] == 2  # name='A' 出现 2 次

    # ---------- 5. 写 Excel ----------
    output_xlsx = tmp_path / "result.xlsx"
    xlsx_out = write_excel.invoke({
        "csv_path": str(result_csv),
        "output_path": str(output_xlsx),
        "sheet_name": "Duplicated",
    })
    assert "error" not in xlsx_out
    assert xlsx_out["output_path"].endswith("result.xlsx")
    assert xlsx_out["size_bytes"] > 0
    assert set(xlsx_out["columns"]) == {"id", "name", "price", "region"}
    assert output_xlsx.exists()

    # ---------- 6. 验证 xlsx 样式 ----------
    wb = load_workbook(output_xlsx)
    ws = wb["Duplicated"]
    # 表头加粗
    header_cell = ws.cell(row=1, column=1)
    assert header_cell.font.bold is True
    # 表头有填充色
    assert header_cell.fill.fgColor.rgb is not None
    # 冻结首行
    assert ws.freeze_panes == "A2"
    # 数据行
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(rows) == 2
    # 第一列是 id
    assert rows[0][0] in (1, 3)


def test_full_pipeline_aggregate(tmp_path):
    """另一个常见场景:groupby 聚合。"""
    zip_bytes = _make_zip_bytes({
        "orders.csv": "region,amount\nA,100\nA,200\nB,150\nB,50\n",
    })
    zip_path = tmp_path / "orders.zip"
    zip_path.write_bytes(zip_bytes)

    work_dir = tmp_path / "w2"
    unzip_out = unzip_archive.invoke({
        "zip_path": str(zip_path),
        "dest_dir": str(work_dir),
    })
    csv_dir = Path(unzip_out["dest_dir"])

    code = (
        "RESULT_DF = orders.groupby('region', as_index=False)['amount'].sum()\n"
        "RESULT_DF = RESULT_DF.sort_values('region')\n"
    )
    result_csv = tmp_path / "agg.csv"
    pd_out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": unzip_out["csv_files"],
        "output_csv": str(result_csv),
    })
    assert pd_out["ok"] is True
    assert pd_out["result_summary"]["row_count"] == 2

    output_xlsx = tmp_path / "agg.xlsx"
    xlsx_out = write_excel.invoke({
        "csv_path": str(result_csv),
        "output_path": str(output_xlsx),
    })
    assert output_xlsx.exists()
    wb = load_workbook(output_xlsx)
    rows = list(wb.active.iter_rows(min_row=2, values_only=True))
    # region=A 应为 300,region=B 应为 200
    by_region = {r[0]: r[1] for r in rows}
    assert by_region["A"] == 300
    assert by_region["B"] == 200