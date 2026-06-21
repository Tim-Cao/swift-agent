"""Checkpointer 工厂(开发期 InMemorySaver,生产可切 PostgresSaver)。

通过 create_deep_agent(checkpointer=...) 在编译期注入;
thread 级 state 持久化由 LangGraph Pregel 框架根据 thread_id 自动完成。
"""

from __future__ import annotations

import os

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver


def get_checkpointer() -> BaseCheckpointSaver:
    backend = os.getenv("CHECKPOINTER_BACKEND", "memory").lower()
    if backend == "memory":
        return InMemorySaver()
    if backend == "postgres":
        # 生产示例:pip install langgraph-checkpoint-postgres
        # from langgraph.checkpoint.postgres import PostgresSaver
        # return PostgresSaver.from_conn_string(os.getenv("CHECKPOINT_DB_URL", ""))
        raise NotImplementedError("PostgresSaver wiring TBD")
    raise ValueError(f"unknown CHECKPOINTER_BACKEND={backend}")


__all__ = ["get_checkpointer"]
