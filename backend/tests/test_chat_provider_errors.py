"""v8.10:chat_service._classify_stream_error 把异常翻译成友好的 user_message。

覆盖:
  - openai.InternalServerError → 上游 5xx 友好提示
  - APITimeoutError / APIConnectionError → 超时/网络友好提示
  - RateLimitError → 限流友好提示
  - 字符串兜底:raw 字符串里出现 "500 internal server" / "timeout" /
    "connection error" 也走 provider 分类
  - 业务错误(普通 ValueError 等) → 原样保留
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.chat_service import _classify_stream_error


# --------------------------------------------------------------------------- #
# 1) openai SDK 异常的精确匹配
# --------------------------------------------------------------------------- #


def _fake_response(status_code: int = 500):
    """构造一个 minimal response mock,openai 异常类只访问 .request。"""
    return SimpleNamespace(
        status_code=status_code,
        request=SimpleNamespace(method="POST", url="https://api.example/v1/x"),
        headers={},
    )


def test_classify_openai_internal_server_error():
    """500 Internal Server Error → 友好提示,code=provider_5xx"""
    try:
        from openai import InternalServerError
    except ImportError:
        import pytest
        pytest.skip("openai SDK not installed")

    e = InternalServerError(
        "Error code: 500 - {'type':'error','error':{'type':'server_error',"
        "'message':'unknown error, 999 (1000)','http_code':'500'}}",
        response=_fake_response(500), body=None,
    )
    out = _classify_stream_error(e)
    assert out["code"] == "provider_5xx"
    assert "上游" in out["user_message"]
    assert "请稍后重试" in out["user_message"]
    assert out["log_level"] == "warning"


def test_classify_openai_timeout():
    try:
        from openai import APITimeoutError
    except ImportError:
        import pytest
        pytest.skip("openai SDK not installed")

    e = APITimeoutError(request=SimpleNamespace(method="POST", url="x"))
    out = _classify_stream_error(e)
    assert out["code"] == "provider_timeout"
    assert "超时" in out["user_message"]
    assert out["log_level"] == "warning"


def test_classify_openai_connection_error():
    try:
        from openai import APIConnectionError
    except ImportError:
        import pytest
        pytest.skip("openai SDK not installed")

    e = APIConnectionError(request=SimpleNamespace(method="POST", url="x"))
    out = _classify_stream_error(e)
    assert out["code"] == "provider_connection"
    assert out["log_level"] == "warning"


def test_classify_openai_rate_limit():
    try:
        from openai import RateLimitError
    except ImportError:
        import pytest
        pytest.skip("openai SDK not installed")

    e = RateLimitError(
        "rate limit", response=_fake_response(429), body=None,
    )
    out = _classify_stream_error(e)
    assert out["code"] == "provider_rate_limit"
    assert "频率" in out["user_message"] or "限" in out["user_message"]
    assert out["log_level"] == "warning"


# --------------------------------------------------------------------------- #
# 2) 字符串兜底(SDK 没装或包装类)
# --------------------------------------------------------------------------- #


def test_classify_string_fallback_500():
    """即便不是 openai 异常类,字符串里出现 500 + internalserver 也走 provider_5xx"""
    class FakeErr(Exception):
        pass

    e = FakeErr(
        "openai.InternalServerError: Error code: 500 - "
        "{'type':'error','error':{'type':'server_error',"
        "'message':'unknown error, 999 (1000)','http_code':'500'}}"
    )
    out = _classify_stream_error(e)
    assert out["code"] == "provider_5xx"
    assert out["log_level"] == "warning"


def test_classify_string_fallback_timeout():
    e = Exception("asyncio.TimeoutError: read timed out")
    out = _classify_stream_error(e)
    assert out["code"] == "provider_timeout"


def test_classify_string_fallback_connection():
    e = Exception("ConnectionError: Connection refused by upstream")
    out = _classify_stream_error(e)
    assert out["code"] == "provider_connection"


# --------------------------------------------------------------------------- #
# 3) 业务/未知错误 → 原样保留
# --------------------------------------------------------------------------- #


def test_classify_value_error_passes_through():
    e = ValueError("RESULT_DF column 'foo' not found")
    out = _classify_stream_error(e)
    assert out["code"] == "internal"
    assert "RESULT_DF" in out["user_message"]
    assert out["log_level"] == "exception"


def test_classify_runtime_error_passes_through():
    e = RuntimeError("deepagents recursion limit exceeded")
    out = _classify_stream_error(e)
    assert out["code"] == "internal"
    assert "recursion" in out["user_message"]
    assert out["log_level"] == "exception"


def test_classify_arbitrary_message_kept_verbatim():
    """未识别的字符串错误 → 原样,不强行套 provider 模板。"""
    e = Exception("no module named 'foo'")
    out = _classify_stream_error(e)
    assert out["code"] == "internal"
    assert out["user_message"] == "no module named 'foo'"