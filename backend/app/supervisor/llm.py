"""ChatOpenAI 固定模板工厂(build_chat_model)。"""

from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from app.core.config import LLMSettings


def build_chat_model(settings: LLMSettings) -> ChatOpenAI:
    """根据 settings 构造 ChatOpenAI 客户端(显式关键字传参)。

    关键:
      - http_client=httpx.Client(verify=False):开发环境信任自签证书
      - extra_body={"thinking": {"type": "disabled"}}:默认关闭思考模式
      - 不再传 max_tokens/timeout(以服务端默认 / 用户后续扩展为准)
    """
    return ChatOpenAI(
        model=settings.model,
        temperature=settings.temperature,
        api_key=settings.api_key,
        base_url=settings.base_url,
        http_client=httpx.Client(verify=False),
        extra_body={"thinking": {"type": "disabled"}},
    )


__all__ = ["build_chat_model"]
