"""中间件管道。

Middleware 协议(项目内旧版,仅作 duck typing 提示):
    async def __call__(ctx, call_next) -> result

deepagents 真正使用的是 langchain.agents.middleware.types.AgentMiddleware。

v11:不再用全局可变列表 ``ALL_MIDDLEWARES`` —— 每个 agent 各自构建一份
中间件列表(``build_middlewares()``),避免不同 agent 之间互相污染,
也避免全局状态导致的测试互相干扰。
"""

from __future__ import annotations

from typing import Any, Awaitable, Protocol


# Middleware 协议(运行时使用 duck typing,这里仅作类型提示)
class Middleware(Protocol):
    """中间件协议。"""

    async def __call__(self, ctx: Any, call_next: Awaitable[Any]) -> Any:  # pragma: no cover
        ...


def build_middlewares() -> list[Any]:
    """构造本项目默认的中间件列表(每次调用返回新实例)。

    当前包含:
      - WebSearchGateMiddleware:根据每轮请求的 web_search_enabled 过滤 MCP 工具

    若 MCP 尚未初始化(MCP init 失败 / 跳过),仍注册一个空 gated 集合的
    WebSearchGateMiddleware —— agent 构建不会因此失败;只是关闭开关时
    没有工具可过滤。
    """
    from middlewares.web_search_gate import WebSearchGateMiddleware

    gated: frozenset[str] = frozenset()
    try:
        from app.core.mcp import get_mcp_tool_names

        gated = get_mcp_tool_names()
    except RuntimeError:
        # MCP 未初始化(lifespan 失败或尚未执行);先注册空集合版本,
        # 等后续就绪再由调用方注入真实工具名
        pass

    return [
        WebSearchGateMiddleware(
            gated_tool_names=gated,
            config_key="web_search_enabled",
        )
    ]


__all__ = ["Middleware", "build_middlewares"]
