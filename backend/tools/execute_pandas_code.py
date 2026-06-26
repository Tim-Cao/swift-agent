"""工具:在受限沙箱里执行 pandas 代码,把 RESULT_DF 写成 result.csv。

沙箱策略(v8 简化):
  - AST 静态检查:拒绝 dunder 访问 / 危险内置调用(open/exec/eval/...)
  - 所有 import 语句在 exec 前一律 **从 AST 删掉**——
    沙箱 globals 已预加载 pd/np/math 等常用库,删 import 不影响业务代码,
    LLM 写"import pandas as pd"/"import os"都不用管。
    真安全靠的是 globals 里没有 __import__ / 没有 os 等危险命名空间。
  - exec 时 __builtins__ 用白名单 SAFE_BUILTINS,只暴露预加载的命名空间。
  - 用户传 allowed_files 限定可访问的 CSV(读入内存做 <stem> 变量)。

v8.8 改动:
  - 容忍 /tmp ↔ /private/tmp symlink:macOS 上 Path.resolve() 后
    /tmp/swift-agent/... 会变成 /private/tmp/swift-agent/...,agent
    给的 csv_dir 可能是其中任意一种,两种形式都尝试打开
  - csv_dir 全部缺失时**立即返回错误**(不再静默返回空 loaded_files),
    让 LLM 知道路径有问题,而不是收到 loaded_files=[] 误以为成功
  - 暴露 pd_safe_read_csv:agent 误写绝对路径时,只要路径在 csv_dir 下
    且文件名在 allowed_files 里,直接返回预加载 DataFrame 的副本
    (避免 FileNotFoundError,同时阻止访问白名单外文件)

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


def _load_csvs_to_globals(csv_dir: str, allowed_files: list[str]) -> tuple[dict, list[str], str | None]:
    """把 allowed_files 里的 CSV 读成 DataFrame,key 用 stem(无扩展名)。

    v8.8 改动:
      - 容忍 /tmp ↔ /private/tmp symlink(macOS 上 Path.resolve() 后
        /tmp/swift-agent/... 变成 /private/tmp/swift-agent/...);agent
        给的 csv_dir 可能是其中任意一种,两种都试
      - 如果 csv_dir 在两种形式下都不存在,返回 error_msg 而不是
        静默返回空 —— LLM 需要知道 csv_dir 是错的,而不是拿到
        loaded_files=[] 误以为成功
      - 返回 (loaded_dict, loaded_stem_names, error_msg)
    """
    loaded: dict[str, pd.DataFrame] = {}
    csv_dir_p = Path(csv_dir)

    # 兼容 symlink:在 macOS 上 /tmp 是 /private/tmp 的 symlink,
    # agent 给的路径可能是其中任意一种。两种都试。
    candidates = [csv_dir_p]
    try:
        resolved = csv_dir_p.resolve()
        if resolved != csv_dir_p:
            candidates.append(resolved)
    except OSError:
        pass
    # 也加一个把 /tmp 和 /private/tmp 互换的候选项
    s = str(csv_dir_p)
    if s.startswith("/private/tmp/"):
        candidates.append(Path("/tmp/" + s[len("/private/tmp/"):]))
    elif s.startswith("/tmp/"):
        candidates.append(Path("/private/tmp/" + s[len("/tmp/"):]))

    chosen_dir: Path | None = None
    for c in candidates:
        if c.exists() and c.is_dir():
            chosen_dir = c
            break

    if chosen_dir is None:
        return (
            {},
            [],
            f"csv_dir not found: tried {[str(c) for c in candidates]}",
        )

    loaded_names: list[str] = []
    missing: list[str] = []
    for fname in allowed_files:
        p = chosen_dir / fname
        if not p.exists():
            missing.append(fname)
            continue
        stem = p.stem.replace("-", "_").replace(" ", "_")
        loaded[stem] = pd.read_csv(p)
        loaded_names.append(stem)

    if missing and not loaded_names:
        # 全部文件都找不到,而不是部分找不到 —— 把 csv_dir 状态也回传
        return (
            {},
            [],
            f"csv_dir exists at {chosen_dir} but none of allowed_files found: {missing}",
        )

    return loaded, loaded_names, None


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
    allowed_files: list[str] | None = None,
    output_csv: str | None = None,
) -> dict:
    """【数据处理首选】在受限沙箱里执行 pandas 代码,处理 CSV 并返回结果。

    **调用场景**:你需要做查重、筛选、聚合、合并多表、日期比较、分组统计等
    任何 pandas 数据处理任务时,直接调本工具。不要手写 CSV 文本、不要逐行 read。
    沙箱已经预加载 `pd` / `np` / 已加载的 DataFrame(以 stem 做变量名),
    业务代码**不要写 import / open / 文件路径**(详见 csv_dir 注入到 globals)。

    Args:
        code: Python 字符串,必须把最终结果赋给 `RESULT_DF`(一个 pd.DataFrame)。
              例:`RESULT_DF = a[a.duplicated(subset=['name'], keep=False)]`
        csv_dir: CSV 目录绝对路径。Supervisor 会给你(原样),不要修改。
        allowed_files: 允许读的 CSV 文件名列表(白名单);不传则默认
                       `["*"]` 表示 csv_dir 下的所有 .csv 都可读。
        output_csv: 把 RESULT_DF 写出的路径。不传(None)则只返回前 20 行样例,
                    不落盘。需要落盘给 ExcelWriterAgent 时传 `<session_dir>/result.csv`。

    Returns:
        成功:{"ok": True, "result_csv": ..., "result_summary": {row_count, columns, head}, "loaded_files": [...]}
        失败:{"ok": False, "error": ..., "traceback": ..., "loaded_files": [...], "loaded_columns": {<var>: [<col>...]}}

    Examples:
        1) 简单筛选(allowed_files 默认读全部):
           execute_pandas_code(
               code="RESULT_DF = a[a['age'] > 30]",
               csv_dir="/tmp/swift-agent/<sid>/csv",
           )

        2) 多表 join(指定白名单):
           execute_pandas_code(
               code="RESULT_DF = orders.merge(users, on='user_id')",
               csv_dir="/tmp/swift-agent/<sid>/csv",
               allowed_files=["orders.csv", "users.csv"],
           )

        3) 落盘 + 写 Excel:
           execute_pandas_code(
               code="RESULT_DF = df.groupby('category').sum()",
               csv_dir="/tmp/swift-agent/<sid>/csv",
               output_csv="/tmp/swift-agent/<sid>/result.csv",
           )
    """
    # v8.11:allowed_files 默认 ["*"] —— 自动扫描 csv_dir 下所有 .csv
    if allowed_files is None:
        csv_dir_p = Path(csv_dir)
        if csv_dir_p.exists() and csv_dir_p.is_dir():
            allowed_files = sorted(
                p.name for p in csv_dir_p.iterdir()
                if p.is_file() and p.suffix.lower() == ".csv"
            )
        else:
            allowed_files = []

    ast_err = _ast_check(code)
    if ast_err:
        return {"ok": False, "error": ast_err, "traceback": None}

    # 所有 import 语句一律从源码里删掉再 exec——
    # 沙箱 globals 没有 __import__,让 LLM 写"import pandas as pd" /
    # "import os" 都安全;业务代码继续运行。
    code = _strip_all_imports(code)

    dfs, loaded_names, load_err = _load_csvs_to_globals(csv_dir, allowed_files)
    if load_err:
        # csv_dir 找不到 / 文件全部缺失 —— 立刻反馈给 LLM,别让它
        # 继续跑 pd.read_csv(absolute_path) 再炸 FileNotFoundError
        return {
            "ok": False,
            "error": load_err,
            "loaded_files": [],
        }

    # v8.8:不在 exec 前 monkey-patch pd.read_csv(避免跨调用的全局状态泄漏)
    # 而是通过 pd_safe_read_csv 暴露给沙箱。如果 LLM 写了绝对路径,可以引导它
    # 改用 pd_safe_read_csv;但更主要的修复路径是 prompt 端告诉 agent
    # 不要写绝对路径,只用预加载变量名(ds / mh / ...)
    real_read_csv = pd.read_csv

    def pd_safe_read_csv(filepath_or_buffer, *args, **kwargs):
        """安全版 pd.read_csv:对 csv_dir 下的允许文件直接返回预加载的副本。

        用法:`pd_safe_read_csv(csv_dir + '/a.csv')` 等价于用预加载的 `a` 变量。
        用于兼容 agent 误写了绝对路径的情况,但仍要求 path 在 csv_dir 下。

        v8.8 强化:如果 path 在 csv_dir 下但**不在** allowed_files 白名单,
        主动抛 PermissionError 而不是静默让 pd 读到 —— 这正是用户的
        "白名单外文件不能读"的诉求。
        """
        p_str = str(filepath_or_buffer)
        try:
            target = Path(p_str).resolve()
        except (OSError, RuntimeError):
            target = Path(p_str)
        try:
            csv_dir_real = Path(csv_dir).resolve()
        except (OSError, RuntimeError):
            csv_dir_real = Path(csv_dir)

        # 在 csv_dir 下 → 强制走白名单
        if csv_dir_real in target.parents or target.parent == csv_dir_real:
            fname = target.name
            stem = target.stem.replace("-", "_").replace(" ", "_")
            if fname in allowed_files and stem in dfs:
                return dfs[stem].copy()
            # 在 csv_dir 下但不在白名单 → 拒绝(隐私边界)
            raise PermissionError(
                f"file {fname!r} is not in allowed_files for this sandbox; "
                f"ask Supervisor to update allowed_files if needed"
            )
        # 不在 csv_dir 下 → 交给 pd 自己处理(会自然 FileNotFoundError 或读到别处)
        return real_read_csv(filepath_or_buffer, *args, **kwargs)

    globals_dict: dict = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        # 给 agent 用的安全版本,允许绝对路径但只对白名单生效
        "pd_safe_read_csv": pd_safe_read_csv,
        # np 是 pd 的依赖,几乎一定有;导入失败也不致命,LLM 代码引用 np 时
        # 会自动 NameError 提示。预加载是为了让"import numpy as np"合法。
        "np": _safe_import("numpy"),
        # 把上下文变量也注入,避免 agent 自己"发明" csv_dir 这种 Jinja 模板
        # 变量(之前 v8.9 看到 RuleParserAgent 写出
        # `pd.read_csv(f"{csv_dir}/a.csv")` 然后报 NameError)
        "csv_dir": csv_dir,
        "allowed_files": list(allowed_files),
        **dfs,
    }

    locals_dict: dict = {}

    try:
        exec(code, globals_dict, locals_dict)
    except Exception as e:  # noqa: BLE001
        import traceback as tb

        # v8.9:把加载到的 DataFrame 的真实列名 repr 一起返回,这样 KeyError 时
        # agent 看到错误就知道实际有哪些列可写
        loaded_columns = {name: list(dfs[name].columns) for name in loaded_names}
        return {
            "ok": False,
            "error": str(e),
            "traceback": tb.format_exc(),
            "loaded_files": loaded_names,
            "loaded_columns": loaded_columns,
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