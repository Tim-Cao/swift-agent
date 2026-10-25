"""项目内置工具包。

import 本子包即可一次性注册 unzip_archive / inspect_csv / execute_pandas_code /
write_excel 四个工具到 tools.TOOLKIT。

约定:__all__ 列出的名字 = TOOLKIT 的 key = 业务调用 get_tools() 用的名字。

import 触发原理:`from tools.builtin.unzip import unzip_archive` 会执行
tools.builtin.unzip 模块顶层代码(其中包含
`register_tool("unzip_archive", unzip_archive, ...)`),所以这一行同时完成了
"触发注册"和"re-export 函数"两件事,不需要单独的 side-effect import。
"""

from tools.builtin.inspect_csv import inspect_csv
from tools.builtin.execute_pandas_code import execute_pandas_code
from tools.builtin.unzip import unzip_archive
from tools.builtin.write_excel import write_excel

__all__ = [
    "unzip_archive",
    "inspect_csv",
    "execute_pandas_code",
    "write_excel",
]
