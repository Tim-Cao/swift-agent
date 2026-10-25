"""工具注册中心。

统一目录结构:
    tools/
      ├── builtin/          项目内置工具(代码在仓库里,前端只读不可编辑)
      │   ├── unzip.py
      │   ├── inspect_csv.py
      │   ├── execute_pandas_code.py
      │   └── write_excel.py
      └── uploaded/         用户上传 zip 解压后的工具模块(运行时生成,不入库)

注册中心维护两张表:
    TOOLKIT      { name: BaseTool }        —— 工具实例,传给 create_deep_agent
    TOOL_META    { name: ToolMeta }        —— 显示名 / 描述 / 是否内置,用于写 DB

新增内置工具:
    from tools import register_tool
    from langchain_core.tools import tool

    @tool
    def my_tool(q: str) -> str:
        '''工具说明'''
        return "result"

    register_tool("my_tool", my_tool, display_name="我的工具", builtin=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


@dataclass
class ToolMeta:
    """工具的展示元数据(与工具实例分离,便于序列化进 DB)。"""

    name: str
    display_name: str = ""
    description: str = ""
    builtin: bool = False
    source_dir: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# 全局工具表:{ name: BaseTool 实例 }
TOOLKIT: dict[str, "BaseTool"] = {}

# 工具元数据:{ name: ToolMeta }
TOOL_META: dict[str, ToolMeta] = {}


def register_tool(
    name: str,
    tool: "BaseTool",
    *,
    display_name: str | None = None,
    description: str | None = None,
    builtin: bool = False,
    source_dir: str | None = None,
) -> None:
    """注册一个具名工具(同名覆盖)。

    description 缺省时取 LangChain tool 的 description(即 docstring),
    这样内置工具不必重复写一遍描述。
    """
    TOOLKIT[name] = tool
    TOOL_META[name] = ToolMeta(
        name=name,
        display_name=display_name or name,
        description=(
            description
            if description is not None
            else (getattr(tool, "description", "") or "")
        ),
        builtin=builtin,
        source_dir=source_dir,
    )


def get_tools(names: list[str]) -> list["BaseTool"]:
    """根据名称列表返回工具实例(未注册则跳过)。"""
    return [TOOLKIT[n] for n in names if n in TOOLKIT]


def get_tool_meta(name: str) -> ToolMeta | None:
    """取工具的展示元数据。"""
    return TOOL_META.get(name)


def list_tool_meta() -> list[ToolMeta]:
    """列出全部已注册工具的元数据。"""
    return sorted(TOOL_META.values(), key=lambda m: (not m.builtin, m.name))


def unregister_tool(name: str) -> None:
    """注销一个工具(用户上传的工具被删除时用)。"""
    TOOLKIT.pop(name, None)
    TOOL_META.pop(name, None)


__all__ = [
    "TOOLKIT",
    "TOOL_META",
    "ToolMeta",
    "register_tool",
    "get_tools",
    "get_tool_meta",
    "list_tool_meta",
    "unregister_tool",
]
