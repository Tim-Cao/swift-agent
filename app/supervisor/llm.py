"""ChatOpenAI 固定模板工厂。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import LLMSettings


def build_chat_openai(settings: LLMSettings) -> ChatOpenAI:
    """根据 settings 构造 ChatOpenAI 客户端(固定传参模板)。"""
    kwargs: dict = {
        "model": settings.model,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "timeout": settings.timeout,
    }
    if settings.api_key:
        kwargs["api_key"] = settings.api_key
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return ChatOpenAI(**kwargs)
