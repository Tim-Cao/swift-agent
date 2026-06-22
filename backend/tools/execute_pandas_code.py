"""工具:在受限沙箱里执行 pandas 代码,把 RESULT_DF 写成 result.csv。

沙箱策略:
  - AST 静态检查:拒绝 import / open / __ dunder 访问 / os / subprocess / sys
  - exec 时禁用 __builtins__,只暴露 pandas + 已加载的 DataFrame(以文件名做 key)
  - 用户传 allowed_files 限定可访问的 CSV(读入内存做 df_<stem>)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

from tools import register_tool


# 允许的内置函数(沙箱白名单)
SAFE_BUILTINS = {
    "len": len,
    "range": range,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "True": True,
    "False": False,
    "None": None,
    "isinstance": isinstance,
    "print": print,
}


def _ast_check(code: str) -> str | None:
    """AST 静态检查;返回 None 表示通过,否则返回错误信息。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # 禁止 import / from ... import
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return f"Import not allowed at line {node.lineno}"
        # 禁止 dunder 访问 / __class__ / __import__ / __builtins__
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"Dunder attribute not allowed: {node.attr} at line {node.lineno}"
        if isinstance(node, ast.Name) and node.id.startswith("_") and node.id not in {"_"}:
            return f"Dunder name not allowed: {node.id} at line {node.lineno}"
        # 禁止 open / file 内置
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"open", "exec", "eval", "compile", "__import__"}:
                return f"Call not allowed: {node.func.id} at line {node.lineno}"
    return None


def _load_csvs_to_globals(csv_dir: str, allowed_files: list[str]) -> tuple[dict, list[str]]:
    """把 allowed_files 里的 CSV 读成 DataFrame,key 用 stem(无扩展名)。"""
    loaded: dict[str, pd.DataFrame] = {}
    csv_dir_p = Path(csv_dir)
    loaded_names: list[str] = []
    for fname in allowed_files:
        p = csv_dir_p / fname
        if not p.exists():
            continue
        stem = p.stem.replace("-", "_").replace(" ", "_")
        loaded[stem] = pd.read_csv(p)
        loaded_names.append(stem)
    return loaded, loaded_names


@tool
def execute_pandas_code(
    code: str,
    csv_dir: str,
    allowed_files: list[str],
    output_csv: str | None = None,
) -> dict:
    """在受限沙箱里执行 pandas 代码。

    Args:
        code: Python 代码,必须把最终结果赋给 RESULT_DF
        csv_dir: CSV 所在目录
        allowed_files: 允许访问的文件名列表(仅这些会被读入内存)
        output_csv: 把 RESULT_DF 写出的路径;若 None 则只返回前 20 行样例

    Returns:
        {"ok": bool, "result_csv": str|None, "result_summary": {...}|None, "error": str|None, "traceback": str|None}
    """
    ast_err = _ast_check(code)
    if ast_err:
        return {"ok": False, "error": ast_err, "traceback": None}

    dfs, loaded_names = _load_csvs_to_globals(csv_dir, allowed_files)

    globals_dict: dict = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        **dfs,
    }
    locals_dict: dict = {}

    try:
        exec(code, globals_dict, locals_dict)
    except Exception as e:  # noqa: BLE001
        import traceback as tb

        return {
            "ok": False,
            "error": str(e),
            "traceback": tb.format_exc(),
            "loaded_files": loaded_names,
        }

    result_df = locals_dict.get("RESULT_DF")
    if result_df is None:
        result_df = globals_dict.get("RESULT_DF")
    if result_df is None or not isinstance(result_df, pd.DataFrame):
        return {
            "ok": False,
            "error": "RESULT_DF not assigned or not a DataFrame",
            "loaded_files": loaded_names,
        }

    result_csv_path = None
    if output_csv:
        out_p = Path(output_csv)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_csv(out_p, index=False)
        result_csv_path = str(out_p.resolve())

    return {
        "ok": True,
        "result_csv": result_csv_path,
        "loaded_files": loaded_names,
        "result_summary": {
            "row_count": int(len(result_df)),
            "columns": list(result_df.columns),
            "head": result_df.head(5).fillna("").astype(str).to_dict(orient="records"),
        },
    }


register_tool("execute_pandas_code", execute_pandas_code)