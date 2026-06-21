"""运行时上下文(context_schema)。

通过 create_deep_agent(context_schema=AppContext) 注入编译期类型;
运行时由 agent.stream_events(input, context=AppContext(...)) 传入实例。
tool/middleware 可通过 runtime: ToolRuntime[AppContext, AgentState] 读取。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppContext:
    """业务级运行时上下文。

    字段:
      session_id: 当前会话 id(同时作为 LangGraph thread_id)
      user_id:    调用方用户标识(可选)
      tenant:     多租户隔离标识(可选)
    """

    session_id: str
    user_id: str | None = None
    tenant: str | None = None


__all__ = ["AppContext"]
