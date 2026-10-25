"""ChatOpenAI 固定模板工厂(build_chat_model)。"""

from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from app.core.config import LLMSettings
from app.services.llm_payload import env_thinking_override, thinking_extra_body


def build_chat_model(settings: LLMSettings) -> ChatOpenAI:
    """根据 settings 构造 ChatOpenAI 客户端(显式关键字传参)。

    关键:
      - http_client=httpx.Client(verify=False):开发环境信任自签证书
      - extra_body 按需带 MiniMax 的 thinking 参数(见 app/services/llm_payload.py):
        硬编码 ``{"thinking": {"type": "disabled"}}`` 会让 MiniMax-M3.1-Flash 直接 400
      - 不再传 max_tokens/timeout(以服务端默认 / 用户后续扩展为准)
    """
    return ChatOpenAI(
        model=settings.model,
        temperature=settings.temperature,
        api_key=settings.api_key,
        base_url=settings.base_url,
        http_client=httpx.Client(verify=False),
        extra_body=thinking_extra_body(
            model=settings.model,
            base_url=settings.base_url,
            override=env_thinking_override(),
        ),
    )


__all__ = ["build_chat_model"]
