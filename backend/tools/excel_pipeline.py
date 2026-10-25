"""Excel pipeline tools 一站式注册(向后兼容入口)。

v10:工具实现已移到统一目录 ``tools/builtin/``;本模块保留为 re-export,
让 ``from tools import excel_pipeline`` 的公开接口继续可用。

约定:__all__ 列出的名字 = TOOLKIT 的 key = 业务调用 get_tools() 用的名字。
"""

from tools.builtin import (
    execute_pandas_code,
    inspect_csv,
    unzip_archive,
    write_excel,
)

__all__ = [
    "unzip_archive",
    "inspect_csv",
    "execute_pandas_code",
    "write_excel",
]
