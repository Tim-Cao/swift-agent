"""子 Agent 列表(空骨架)。

新增子 Agent:
    # my_agent.py
    from tools import get_tools

    my_agent = {
        "name": "MyAgent",
        "description": "Agent 描述",
        "system_prompt": "你是 ...",
        "tools": get_tools(["my_tool"]),
        "skills": ["my-skill"],
    }

    # subagents/__init__.py 末尾追加:
    from my_pkg.my_agent import my_agent
    ALL_SUBAGENTS.append(my_agent)
"""

from __future__ import annotations

# 子 Agent 字典列表
ALL_SUBAGENTS: list[dict] = []


__all__ = ["ALL_SUBAGENTS"]
