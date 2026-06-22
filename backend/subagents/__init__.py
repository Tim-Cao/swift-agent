"""子 Agent 列表。

注册中心:把 4 个 Excel pipeline subagent 注册到 ALL_SUBAGENTS。
deepagents 0.6.11 用 task 工具 + LLM 自调度,所以这里只要列出来即可,
串行顺序由 supervisor system_prompt 写明。

新增子 Agent 示例:
    # my_agent.py
    from tools import get_tools

    my_agent = {
        "name": "MyAgent",
        "description": "...",
        "system_prompt": "...",
        "tools": get_tools(["my_tool"]),
        "skills": ["my-skill"],
    }

    # __init__.py 末尾追加:
    from my_agent import my_agent
    ALL_SUBAGENTS.append(my_agent)
"""

from __future__ import annotations

# 触发工具注册(@tool 装饰器在 import 时执行,get_tools 在 subagent 模块
# 顶层被调用,所以注册必须先于 subagent 模块 import)
from tools import excel_pipeline  # noqa: F401

# Excel pipeline subagents
from subagents.intake_agent import INTAKE_AGENT
from subagents.rule_parser_agent import RULE_PARSER_AGENT
from subagents.data_processing_agent import DATA_PROCESSING_AGENT
from subagents.excel_writer_agent import EXCEL_WRITER_AGENT

# 子 Agent 字典列表
ALL_SUBAGENTS: list[dict] = [
    INTAKE_AGENT,
    RULE_PARSER_AGENT,
    DATA_PROCESSING_AGENT,
    EXCEL_WRITER_AGENT,
]


__all__ = ["ALL_SUBAGENTS"]