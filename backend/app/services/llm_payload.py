"""LLM 请求体里的厂商私有扩展(目前只有 MiniMax 的 thinking)。

**为什么需要它**

MiniMax 的 OpenAI 兼容端点支持一个私有参数 ``thinking``:
``{"thinking": {"type": "disabled" | "enabled" | "adaptive"}}``。
但**不是所有模型都接受同样的值**:

- ``MiniMax-M3.1-Flash`` 强制要求 ``adaptive``;传 ``disabled``(或
  ``reasoning.effort=none``)会被服务端拒掉,报 400::

      invalid params, model "MiniMax-M3.1-Flash" requires adaptive thinking;
      thinking.type="disabled" (including reasoning.effort=none) is not allowed

- ``MiniMax-M3`` 只接受 ``disabled`` / ``adaptive``;传 ``enabled`` 会 400。

而 ``thinking`` 是 **MiniMax 私有参数**,发给普通的 OpenAI 兼容端点
(本地 vLLM / Ollama / OpenAI 官方)会被当成未知字段拒掉。

所以这里按「模型名 + base_url」两条线索决定发什么:

1. base_url 看着像 MiniMax → 才带 ``thinking``;
2. 带的话,再按模型名挑值 —— M3.1 系列用 ``adaptive``,其余用 ``adaptive``
   (对 MiniMax 全部模型都是合法值,见 tests/test_llm_payload.py)。

**默认值**

``LLM_THINKING_TYPE`` 可以显式指定(``disabled`` / ``enabled`` / ``adaptive``),
留空则走上面的自动判断。显式指定时优先级最高,方便用户覆盖。
"""

from __future__ import annotations

import os

# MiniMax 的 base_url 特征
_MINIMAX_URL_HINTS = ("minimaxi.com", "minimax.io", "minimaxi.chat")

# 这些模型强制要 adaptive
_ADAPTIVE_ONLY_HINTS = ("m3.1",)


def _looks_like_minimax(base_url: str | None) -> bool:
    if not base_url:
        return False
    url = base_url.lower()
    return any(h in url for h in _MINIMAX_URL_HINTS)


def _needs_adaptive(model: str | None) -> bool:
    if not model:
        return False
    return any(h in model.lower() for h in _ADAPTIVE_ONLY_HINTS)


def resolve_thinking_type(
    *,
    model: str | None = None,
    base_url: str | None = None,
    override: str | None = None,
) -> str | None:
    """决定这次请求要带什么 ``thinking.type``;返回 None 表示不带。

    参数:
      model:    模型 id(如 ``MiniMax-M3.1-Flash``)
      base_url: 提供商的 OpenAI 兼容端点
      override: 显式指定(``LLM_THINKING_TYPE`` 环境变量 / 显式参数),
                非空时直接返回
    """
    if override:
        return override
    if not _looks_like_minimax(base_url):
        return None
    # adaptive 对 MiniMax 全系都是合法值(实测 M3 / M2.7 / M2.5 都接受),
    # 而 disabled 会被 M3.1-Flash 拒掉、enabled 会被 M3 拒掉 —— adaptive 最稳。
    if _needs_adaptive(model):
        return "adaptive"
    return "adaptive"


def thinking_extra_body(
    *,
    model: str | None = None,
    base_url: str | None = None,
    override: str | None = None,
) -> dict:
    """构造 ChatOpenAI 的 ``extra_body``;不需要扩展时返回 ``{}``。"""
    thinking = resolve_thinking_type(
        model=model, base_url=base_url, override=override
    )
    if not thinking:
        return {}
    return {"thinking": {"type": thinking}}


def env_thinking_override() -> str | None:
    """读 ``LLM_THINKING_TYPE``(可选覆盖)。"""
    val = os.environ.get("LLM_THINKING_TYPE", "").strip()
    return val or None


__all__ = [
    "resolve_thinking_type",
    "thinking_extra_body",
    "env_thinking_override",
]
