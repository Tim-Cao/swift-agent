"""WebSearchGateMiddleware:按每轮请求的 web_search_enabled 配置过滤 MCP 工具。

原理:
  - deepagents 的 AgentMiddleware.awrap_model_call 在每次 LLM 调用前触发,
    可以修改 request.tools 后再传给 handler。
  - 通过 langgraph.config.get_config() 拿到 RunnableConfig,读
    configurable.web_search_enabled:True 保留所有工具;False 时把 MCP 工具
    从 request.tools 里剔除,LLM 看不到、也就调不到。
  - MCP 工具始终加载到 supervisor(降低 supervisor 构建开销),由本 middleware
    在运行时决定是否暴露给 LLM。

注册位置:ALL_MIDDLEWARES(在 builder.py 里 use)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langgraph.config import get_config

logger = logging.getLogger(__name__)


def _tool_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


class WebSearchGateMiddleware(AgentMiddleware):
    """在 LLM 调用前,根据 web_search_enabled 过滤 MCP 工具。

    Args:
        gated_tool_names: MCP 工具名集合,这些工具在开关关闭时不会出现在
            LLM 的工具列表中(等价于"未挂载")。
        config_key: configurable 里对应的键名,默认 'web_search_enabled'。
    """

    def __init__(
        self,
        *,
        gated_tool_names: frozenset[str],
        config_key: str = "web_search_enabled",
    ) -> None:
        self._gated = set(gated_tool_names)
        self._config_key = config_key

    def _resolve_enabled(self) -> bool:
        """从 langgraph contextvar 拿 config,读开关值。"""
        try:
            config = get_config()
        except RuntimeError:
            # 不在 runnable context(理论上不会发生,防御性兜底)
            return False
        cfg = config.get("configurable") if isinstance(config, dict) else None
        if not isinstance(cfg, dict):
            return False
        return bool(cfg.get(self._config_key, False))

    def _filter(self, tools: list[Any]) -> list[Any]:
        return [t for t in tools if _tool_name(t) not in self._gated]

    # ------------------------------------------------------------------
    # 同步版本(参考用,deepagents 默认走异步)
    # ------------------------------------------------------------------
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        if self._gated and not self._resolve_enabled():
            filtered = self._filter(list(request.tools))
            if len(filtered) != len(request.tools):
                logger.debug(
                    "WebSearchGate: stripping %d MCP tool(s) (toggle off)",
                    len(request.tools) - len(filtered),
                )
                request = request.override(tools=filtered)
        return handler(request)

    # ------------------------------------------------------------------
    # 异步版本(deepagents 默认走这个)
    # ------------------------------------------------------------------
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        enabled = self._resolve_enabled()
        if self._gated and not enabled:
            before = list(request.tools)
            filtered = self._filter(before)
            if len(filtered) != len(before):
                # 按名字查"被剔除的工具"——不能 set(before):StructuredTool
                # 定义了 __eq__ 但 __hash__=None,塞进 set 会抛
                # "unhashable type: 'StructuredTool'",把整轮 LLM 调用炸掉
                filtered_names = {
                    n for n in (_tool_name(t) for t in filtered) if n
                }
                removed_names = [
                    _tool_name(t) or "?"
                    for t in before
                    if _tool_name(t) not in filtered_names
                ]
                logger.debug(
                    "WebSearchGate: toggle=OFF, stripped %d MCP tool(s): %s",
                    len(before) - len(filtered),
                    removed_names,
                )
                request = request.override(tools=filtered)
        elif self._gated and enabled:
            logger.debug(
                "WebSearchGate: toggle=ON, exposing %d tool(s) including MCP",
                len(request.tools),
            )
        return await handler(request)