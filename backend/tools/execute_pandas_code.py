"""工具:在受限沙箱里执行 pandas 代码,把 RESULT_DF 写成 result.csv。

沙箱策略:
  - AST 静态检查:拒绝非白名单 import / open / __ dunder 访问 / 危险调用
  - exec 时禁用 __builtins__,只暴露预加载的命名空间(pd / np / DataFrame)
  - 用户传 allowed_files 限定可访问的 CSV(读入内存做 <stem> 变量)
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_core.tools import tool

from tools import register_tool


def _safe_import(name: str) -> Any:
    """try-import 工具:库缺失时不抛,返回 None。

    pandas 通常带 numpy(pd 内部用),但保险起见 try 一下。
    """
    try:
        return __import__(name)
    except ImportError:
        return None


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

# 沙箱允许的 import(预加载的库)。LLM 写的代码常含
# `import pandas as pd` / `import numpy as np` 这类无害语句,沙箱已
# 把 pd/np 注入 globals,放行 import 只是为了让代码风格更宽容;
# 真正限制靠的是"沙箱 globals 里没有 os / subprocess / requests 等"。
ALLOWED_IMPORTS = {
    "pandas",          # 已注入为 pd
    "numpy",           # 注入为 np
    "math",            # stdlib,纯计算
    "statistics",      # stdlib,纯计算
    "datetime",        # stdlib,日期处理
    "re",              # stdlib,正则
    "collections",     # stdlib,数据结构
    "itertools",       # stdlib,迭代器
    "functools",       # stdlib,函数工具
}

# 允许的 from-import 源(同 ALLOWED_IMPORTS)
ALLOWED_FROM_MODULES = ALLOWED_IMPORTS | {"pandas", "numpy"}

# 禁止的内置名(可在白名单里再用)
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "breakpoint"}


def _ast_check(code: str) -> str | None:
    """AST 静态检查;返回 None 表示通过,否则返回错误信息。

    规则:
      - import X / from X import Y:X 必须在 ALLOWED_IMPORTS / ALLOWED_FROM_MODULES
      - 禁止 dunder 访问(Attribute.attr / Name.id 以 _ 开头)
      - 禁止调用 BANNED_NAMES(open / exec / eval / compile / __import__)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # import / from-import 白名单
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    return (
                        f"Import not allowed at line {node.lineno}: "
                        f"{alias.name} (allowed: {sorted(ALLOWED_IMPORTS)})"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                # `from . import x` 这类相对导入,直接拒绝
                return f"Relative import not allowed at line {node.lineno}"
            root = node.module.split(".")[0]
            if root not in ALLOWED_FROM_MODULES:
                return (
                    f"Import not allowed at line {node.lineno}: "
                    f"from {node.module} (allowed: {sorted(ALLOWED_FROM_MODULES)})"
                )
            # 即便 module 是白名单,也禁止 `from os import *` / __ 开头名字
            for alias in node.names:
                if alias.name.startswith("_"):
                    return f"Dunder name not allowed: {alias.name} at line {node.lineno}"

        # 禁止 dunder 访问 / __class__ / __import__ / __builtins__
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"Dunder attribute not allowed: {node.attr} at line {node.lineno}"
        if isinstance(node, ast.Name) and node.id.startswith("_") and node.id not in {"_"}:
            return f"Dunder name not allowed: {node.id} at line {node.lineno}"

        # 禁止 open / file 内置
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in BANNED_NAMES:
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


def _strip_whitelisted_imports(code: str) -> str:
    """从 AST 里删掉白名单内的 import 语句,只保留业务代码。

    _ast_check 已保证所有 import 都在白名单内,所以这里直接删。
    沙箱 globals 注入 pd / np / math 等,删了不影响功能,只避免运行时
    NameError(__import__ not in sandbox)。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # 让后续 exec 报 SyntaxError
    new_body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    if len(new_body) == len(tree.body):
        return code  # 没 import,原样返回
    new_tree = ast.Module(body=new_body, type_ignores=[])
    try:
        return ast.unparse(new_tree)
    except Exception:  # noqa: BLE001  Python<3.9 兜底
        return code


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

    # AST 通过后,把白名单内的 import 语句从源码里删掉再 exec——
    # 沙箱 globals 没有 __import__,LLM 写的"import pandas as pd"会
    # NameError。沙箱已预加载 pd/np 等,删 import 不影响功能。
    code = _strip_whitelisted_imports(code)

    dfs, loaded_names = _load_csvs_to_globals(csv_dir, allowed_files)

    globals_dict: dict = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        # np 是 pd 的依赖,几乎一定有;导入失败也不致命,LLM 代码引用 np 时
        # 会自动 NameError 提示。预加载是为了让"import numpy as np"合法。
        "np": _safe_import("numpy"),
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