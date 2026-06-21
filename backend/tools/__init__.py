"""工具注册中心(空骨架)。

新增工具:
    from tools import register_tool
    from langchain_core.tools import tool

    @tool
    def my_tool(q: str) -> str:
        '''工具说明'''
        return "result"

    register_tool("my_tool", my_tool)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

# 全局工具表:{ name: BaseTool 实例 }
TOOLKIT: dict[str, "BaseTool"] = {}


def register_tool(name: str, tool: "BaseTool") -> None:
    """注册一个具名工具(同名覆盖)。"""
    TOOLKIT[name] = tool


def get_tools(names: list[str]) -> list["BaseTool"]:
    """根据名称列表返回工具实例(未注册则跳过)。"""
    return [TOOLKIT[n] for n in names if n in TOOLKIT]


__all__ = ["TOOLKIT", "register_tool", "get_tools"]
