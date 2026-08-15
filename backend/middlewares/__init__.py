"""中间件管道。

Middleware 协议(项目内旧版,仅作 duck typing 提示):
    async def __call__(ctx, call_next) -> result

deepagents 真正使用的是 langchain.agents.middleware.types.AgentMiddleware,
本模块提供 ALL_MIDDLEWARES 列表,在 supervisor.builder 启动时注册。

当前已注册:
  - WebSearchGateMiddleware: 根据每轮请求的 web_search_enabled 过滤 MCP 工具
"""

from __future__ import annotations

from typing import Any, Awaitable, Protocol

# Middleware 协议(运行时使用 duck typing,这里仅作类型提示)
class Middleware(Protocol):
    """中间件协议。"""

    async def __call__(self, ctx: Any, call_next: Awaitable[Any]) -> Any:  # pragma: no cover
        ...


# 默认空列表;具体 middleware 在下面 append 时被注册
ALL_MIDDLEWARES: list[Any] = []

# 延迟导入:避免在 lifespan 之前触发 MCP client 初始化
def _register_default_middlewares() -> None:
    """注册项目内置的中间件。重复调用幂等。

    若 MCP 尚未初始化(MCP init 失败 / 跳过),仍注册一个空 gated 集合的
    WebSearchGateMiddleware——supervisor 构建不会因此失败;只是关闭开关时
    没有工具可过滤。等 MCP 后续就绪,通过重置 gated_tool_names 即可生效。
    """
    from middlewares.web_search_gate import WebSearchGateMiddleware

    if any(isinstance(m, WebSearchGateMiddleware) for m in ALL_MIDDLEWARES):
        return  # 已注册

    gated: frozenset[str] = frozenset()
    try:
        from app.core.mcp import get_mcp_tool_names

        gated = get_mcp_tool_names()
    except RuntimeError:
        # MCP 未初始化(lifespan 失败或尚未执行);先注册空集合版本,
        # 等后续就绪再由调用方注入真实工具名(见 builder._build_agent)
        pass

    ALL_MIDDLEWARES.append(
        WebSearchGateMiddleware(
            gated_tool_names=gated,
            config_key="web_search_enabled",
        )
    )


__all__ = ["Middleware", "ALL_MIDDLEWARES", "_register_default_middlewares"]
