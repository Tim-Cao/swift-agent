"""工具:读 CSV,返回字段名 / 数据类型推断 / 缺失值 / 前 N 行样例。"""

from __future__ import annotations

from pathlib import Path

import chardet
import pandas as pd
from langchain_core.tools import tool

from tools import register_tool


def _detect_encoding(csv_path: Path, sample_bytes: int = 64 * 1024) -> str:
    with csv_path.open("rb") as f:
        raw = f.read(sample_bytes)
    if not raw:
        return "utf-8"
    result = chardet.detect(raw)
    return result.get("encoding") or "utf-8"


def _infer_dtype(series: pd.Series) -> str:
    """简化版类型推断:integer / float / bool / datetime / string。"""
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    # 试一下能不能转日期(只对字符串列试一次)
    if series.dtype == object:
        try:
            pd.to_datetime(series.dropna().head(20), errors="raise")
            return "datetime"
        except (ValueError, TypeError):
            pass
    return "string"


@tool
def inspect_csv(csv_path: str, sample_rows: int = 5) -> dict:
    """读取 CSV,返回结构信息。

    Returns:
        {
          "path": str,
          "encoding": str,
          "row_count": int,
          "column_count": int,
          "columns": [{"name": str, "dtype": str, "missing": int}, ...],
          "sample": [{列名: 值}, ...]
        }
    """
    p = Path(csv_path)
    if not p.exists():
        return {"error": f"csv not found: {csv_path}"}

    encoding = _detect_encoding(p)
    try:
        df = pd.read_csv(p, encoding=encoding)
    except Exception as e:  # noqa: BLE001
        return {"error": f"failed to read csv: {e}"}

    columns = []
    for col in df.columns:
        col_str = df[col]
        columns.append({
            "name": str(col),
            "dtype": _infer_dtype(col_str),
            "missing": int(col_str.isna().sum()),
        })

    sample_df = df.head(sample_rows).fillna("").astype(str)
    return {
        "path": str(p.resolve()),
        "encoding": encoding,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns,
        "sample": sample_df.to_dict(orient="records"),
    }


register_tool("inspect_csv", inspect_csv)