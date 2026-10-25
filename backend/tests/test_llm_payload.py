"""thinking 参数的解析逻辑。

背景:之前所有 LLM 请求都硬编码 ``extra_body={"thinking": {"type": "disabled"}}``。
MiniMax-M3.1-Flash 强制要求 ``adaptive``,传 ``disabled`` 会被服务端 400 拒掉:

    invalid params, model "MiniMax-M3.1-Flash" requires adaptive thinking;
    thinking.type="disabled" (including reasoning.effort=none) is not allowed

而 ``thinking`` 是 MiniMax 私有参数,发给普通 OpenAI 兼容端点反而会被拒。
"""

from __future__ import annotations

import pytest

from app.services.llm_payload import (
    env_thinking_override,
    resolve_thinking_type,
    thinking_extra_body,
)

MINIMAX = "https://api.minimaxi.com/v1"


class TestResolveThinkingType:
    def test_minimax_uses_adaptive(self):
        # adaptive 对 MiniMax 全系都合法;disabled 会被 M3.1 拒、enabled 会被 M3 拒
        assert resolve_thinking_type(model="MiniMax-M3", base_url=MINIMAX) == "adaptive"
        assert (
            resolve_thinking_type(model="MiniMax-M3.1-Flash", base_url=MINIMAX)
            == "adaptive"
        )
        assert resolve_thinking_type(model="MiniMax-M2.7", base_url=MINIMAX) == "adaptive"

    def test_non_minimax_gets_none(self):
        # 普通 OpenAI 兼容端点:不能带 thinking,否则当成未知字段被拒
        assert resolve_thinking_type(model="gpt-4o", base_url="https://api.openai.com/v1") is None
        assert resolve_thinking_type(model="gpt-4o", base_url="http://localhost:8000/v1") is None
        assert resolve_thinking_type(model="llama3", base_url=None) is None

    def test_override_wins(self):
        assert (
            resolve_thinking_type(
                model="MiniMax-M3.1-Flash", base_url=MINIMAX, override="enabled"
            )
            == "enabled"
        )
        # override 对非 minimax 也生效(用户显式指定了就听用户的)
        assert (
            resolve_thinking_type(
                model="gpt-4o", base_url="https://api.openai.com/v1", override="disabled"
            )
            == "disabled"
        )

    def test_empty_override_is_ignored(self):
        assert resolve_thinking_type(model="MiniMax-M3", base_url=MINIMAX, override="") == "adaptive"


class TestThinkingExtraBody:
    def test_minimax_payload(self):
        assert thinking_extra_body(model="MiniMax-M3.1-Flash", base_url=MINIMAX) == {
            "thinking": {"type": "adaptive"}
        }

    def test_non_minimax_payload_is_empty(self):
        assert thinking_extra_body(model="gpt-4o", base_url="https://api.openai.com/v1") == {}

    def test_override_payload(self):
        assert (
            thinking_extra_body(
                model="MiniMax-M3.1-Flash", base_url=MINIMAX, override="enabled"
            )
            == {"thinking": {"type": "enabled"}}
        )


class TestEnvOverride:
    def test_env_not_set(self, monkeypatch):
        monkeypatch.delenv("LLM_THINKING_TYPE", raising=False)
        assert env_thinking_override() is None

    def test_env_set(self, monkeypatch):
        monkeypatch.setenv("LLM_THINKING_TYPE", "adaptive")
        assert env_thinking_override() == "adaptive"

    def test_env_blank_is_ignored(self, monkeypatch):
        monkeypatch.setenv("LLM_THINKING_TYPE", "   ")
        assert env_thinking_override() is None
