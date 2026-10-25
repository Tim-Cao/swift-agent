"""thread config 工具。

v11:原先这些函数在 app/supervisor/builder.py 里,连同硬编码的 supervisor
一起删掉了。builder 的职责(装配 agent)现在完全由 DB 驱动 —— 见
app/services/agent_service.py。
"""

from __future__ import annotations


def make_thread_config(thread_id: str) -> dict:
    """绑定 thread_id 用于 stateful 多轮对话。

    state 数据不由调用方传入,而是由 deepagents 内部 checkpointer
    按 thread_id 自动维护;调用方只通过 config.configurable.thread_id 索引。
    """
    return {"configurable": {"thread_id": thread_id}}


__all__ = ["make_thread_config"]
