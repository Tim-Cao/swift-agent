"""Store 工厂(开发期 InMemoryStore,生产可切 PostgresStore)。

通过 create_deep_agent(store=...) 在编译期注入;
供跨 thread 长期记忆的中间件(如 MemoryMiddleware)使用。
注意:deepagents 不兜底 store,store=None 时相关中间件会抛错。

v5:后端选择由 Pydantic PersistenceSettings(PERSISTENCE_STORE_BACKEND)
收编,不再旁路 os.getenv。
"""

from __future__ import annotations

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.core.config import get_settings


def get_store() -> BaseStore:
    backend = get_settings().persistence.store_backend
    if backend == "memory":
        return InMemoryStore()
    if backend == "postgres":
        # 生产示例:from langgraph.store.postgres import PostgresStore
        raise NotImplementedError(
            "PostgresStore wiring TBD; "
            "set PERSISTENCE_STORE_BACKEND=memory or "
            "wire langgraph-store-postgres"
        )
    raise ValueError(f"unknown PERSISTENCE_STORE_BACKEND={backend}")


__all__ = ["get_store"]