"""Checkpointer 工厂(开发期 InMemorySaver,生产可切 PostgresSaver)。

通过 create_deep_agent(checkpointer=...) 在编译期注入;
thread 级 state 持久化由 LangGraph Pregel 框架根据 thread_id 自动完成。

v5:后端选择由 Pydantic PersistenceSettings(PERSISTENCE_CHECKPOINTER_BACKEND)
收编,不再旁路 os.getenv。
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import get_settings


def get_checkpointer() -> BaseCheckpointSaver:
    backend = get_settings().persistence.checkpointer_backend
    if backend == "memory":
        return InMemorySaver()
    if backend == "postgres":
        # 生产示例:pip install langgraph-checkpoint-postgres
        # from langgraph.checkpoint.postgres import PostgresSaver
        # return PostgresSaver.from_conn_string(
        #     get_settings().persistence.checkpoint_db_url or ""
        # )
        raise NotImplementedError(
            "PostgresSaver wiring TBD; "
            "set PERSISTENCE_CHECKPOINTER_BACKEND=memory or "
            "wire langgraph-checkpoint-postgres"
        )
    raise ValueError(f"unknown PERSISTENCE_CHECKPOINTER_BACKEND={backend}")


__all__ = ["get_checkpointer"]