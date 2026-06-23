"""工具:在受限沙箱里执行 pandas 代码,把 RESULT_DF 写成 result.csv。

沙箱策略(v8 简化):
  - AST 静态检查:拒绝 dunder 访问 / 危险内置调用(open/exec/eval/...)
  - 所有 import 语句在 exec 前一律 **从 AST 删掉**——
    沙箱 globals 已预加载 pd/np/math 等常用库,删 import 不影响业务代码,
    LLM 写"import pandas as pd"/"import os"都不用管。
    真安全靠的是 globals 里没有 __import__ / 没有 os 等危险命名空间。
  - exec 时 __builtins__ 用白名单 SAFE_BUILTINS,只暴露预加载的命名空间。
  - 用户传 allowed_files 限定可访问的 CSV(读入内存做 <stem> 变量)。

为什么 import 不拒绝而是 strip:
  - LLM 生成的代码常带 `import pandas as pd` / `import numpy as np`,
    即便不需要写出来也属于习惯
  - 如果允许 `import os.path as osp`,即便真的执行了,沙箱 globals 没
    __import__ 也会 ImportError——黑名单既繁琐又漏边界
  - 简化:所有 import 一律 strip,业务代码风格自由,沙箱安全不变
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

# 禁止的内置名(可在白名单里再用)
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "breakpoint"}


def _ast_check(code: str) -> str | None:
    """AST 静态检查;返回 None 表示通过,否则返回错误信息。

    规则:
      - 禁止 dunder 访问(Attribute.attr / Name.id 以 _ 开头)
      - 禁止调用 BANNED_NAMES(open / exec / eval / compile / __import__)
      - import 语句**不**在这里拒绝,统一交给 _strip_all_imports 处理
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # 禁止 dunder 访问 / __class__ / __import__ / __builtins__
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"Dunder attribute not allowed: {node.attr} at line {node.lineno}"
        if isinstance(node, ast.Name) and node.id.startswith("_") and node.id not in {"_"}:
            return f"Dunder name not allowed: {node.id} at line {node.lineno}"

        # 禁止 open / exec / eval / compile / __import__ 内置
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


def _strip_all_imports(code: str) -> str:
    """从 AST 里删掉**所有** import 语句,只保留业务代码。

    v8 简化:沙箱 globals 已预加载 pd / np / math 等,真业务根本不需要
    import。LLM 即便写了 `import pandas as pd` / `import os`,这里统一
    strip 掉,exec 时不会触发 __import__,业务代码继续运行。
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

    # 所有 import 语句一律从源码里删掉再 exec——
    # 沙箱 globals 没有 __import__,让 LLM 写"import pandas as pd" /
    # "import os" 都安全;业务代码继续运行。
    code = _strip_all_imports(code)

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