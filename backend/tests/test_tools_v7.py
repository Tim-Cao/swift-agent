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


def test_execute_pandas_code_sandbox_strips_import(csv_dir):
    """v8 简化:所有 import 一律 strip,业务代码继续运行。

    沙箱 globals 没有 __import__,但也不需要真 import——pd/np/math 等
    已预加载。LLM 写 `import os` 不会失败,只是被 AST 删掉;后续如果
    真引用了未注入的 os 才会 NameError,但那属于业务代码问题。
    """
    code = "import os\nRESULT_DF = a.copy()\n"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 3


def test_execute_pandas_code_allows_pandas_import(csv_dir):
    """沙箱已预加载 pd,LLM 写 import pandas as pd 应放行(冗余但无害)。"""
    code = (
        "import pandas as pd\n"
        "import numpy as np\n"
        "RESULT_DF = a.copy()\n"
    )
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 3


def test_execute_pandas_code_allows_stdlib_import(csv_dir):
    """math / datetime / re / collections / itertools 等 stdlib 可 import。"""
    code = (
        "import re\n"
        "import math\n"
        "import datetime\n"
        "RESULT_DF = a.copy()\n"
    )
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out


def test_execute_pandas_code_allows_requests_import(csv_dir):
    """v8:requests / subprocess / sys 等敏感 import 也一律 strip,
    不再被沙箱拒绝。LLM 可以保留自己的代码风格(曾经会因 import requests
    被拒而不得不改写)。"""
    code = "import requests\nRESULT_DF = a.copy()\n"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 3


def test_execute_pandas_code_allows_from_os(csv_dir):
    """v8:`from os import path` 同样被 strip,业务代码继续运行。"""
    code = "from os import path\nRESULT_DF = a.copy()\n"
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 3


def test_execute_pandas_code_strip_keeps_business_code(csv_dir):
    """v8 关键场景:LLM 写 `import os; ... pd.read_csv(...)` 不需要再改写,
    沙箱把 import strip 掉,业务代码继续跑。

    os 被 strip 掉后,业务代码引用 os.path.join 会 NameError——这属于
    业务代码本身的问题(它依赖了未被注入的命名空间),不属于沙箱拒绝。
    这里验的是:有 import 时沙箱不阻拦(strip 之后业务代码能不能继续
    跑靠代码本身)。
    """
    code = (
        "import os\n"
        "RESULT_DF = a.copy()\n"
    )
    out = execute_pandas_code.invoke({
        "code": code,
        "csv_dir": str(csv_dir),
        "allowed_files": ["a.csv"],
    })
    assert out["ok"] is True, out
    assert out["result_summary"]["row_count"] == 3


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