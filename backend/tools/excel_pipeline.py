"""Excel pipeline tools 一站式注册。

import 本子包即可一次性注册 unzip_archive / inspect_csv / execute_pandas_code /
write_excel 四个工具到 tools.TOOLKIT。

约定:__all__ 列出的名字 = TOOLKIT 的 key = 业务调用 get_tools() 用的名字。

import 触发原理:`from tools.unzip import unzip_archive` 会执行 tools.unzip
模块顶层代码(其中包含 `register_tool("unzip_archive", unzip_archive)`),
所以这一行同时完成了"触发注册"和"re-export 函数"两件事,不需要单独的
side-effect import。
"""

from tools.inspect_csv import inspect_csv
from tools.execute_pandas_code import execute_pandas_code
from tools.unzip import unzip_archive
from tools.write_excel import write_excel

__all__ = [
    "unzip_archive",
    "inspect_csv",
    "execute_pandas_code",
    "write_excel",
]
