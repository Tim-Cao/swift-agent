"""模型发现:通过 OpenAI 兼容的 ``/models`` 接口拉取提供商的可用模型。

兼容绝大多数厂商(MiniMax / DeepSeek / Ollama / vLLM / OpenAI 自身),
只要它们暴露 ``GET {base_url}/models`` 并接受 ``Authorization: Bearer {api_key}``。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 发现模型的超时(秒)
DISCOVERY_TIMEOUT = 20.0


class ModelDiscoveryError(Exception):
    """模型发现失败(对外转成 400/502 提示)。"""


def _models_endpoint(base_url: str) -> str:
    """把 base_url 规整成 .../models 端点。"""
    url = base_url.strip().rstrip("/")
    if not url:
        raise ModelDiscoveryError("base_url 为空")
    if url.endswith("/models"):
        return url
    if url.endswith("/v1"):
        return f"{url}/models"
    return f"{url}/v1/models"


async def discover_models(
    base_url: str,
    api_key: str = "",
    *,
    timeout: float = DISCOVERY_TIMEOUT,
    verify_tls: bool = True,
) -> list[dict[str, str]]:
    """拉取提供商的模型列表。

    返回 ``[{"id": "gpt-4o", "name": "gpt-4o"}, ...]``(name 缺省等于 id)。
    抛 ModelDiscoveryError 表示失败(网络/鉴权/格式不对)。

    verify_tls 默认 True(校验证书);仅在连自签证书的私有部署时,
    通过配置项 MODEL_DISCOVERY_VERIFY_TLS=false 关闭校验。
    """
    endpoint = _models_endpoint(base_url)
    headers = {"accept": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify_tls) as client:
            resp = await client.get(endpoint, headers=headers)
    except httpx.HTTPError as e:
        raise ModelDiscoveryError(f"请求失败: {e}") from e

    if resp.status_code == 401 or resp.status_code == 403:
        raise ModelDiscoveryError("鉴权失败(401/403),请检查 API Key")
    if resp.status_code >= 400:
        detail = resp.text[:200]
        raise ModelDiscoveryError(f"提供商返回 {resp.status_code}: {detail}")

    try:
        payload: Any = resp.json()
    except Exception as e:  # noqa: BLE001
        raise ModelDiscoveryError(f"响应不是合法 JSON: {e}") from e

    # OpenAI 兼容格式:{"data": [{"id": "...", ...}, ...]}
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ModelDiscoveryError("响应缺少 data 数组(不是 OpenAI 兼容格式)")

    out: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, str):
            out.append({"id": item, "name": item})
        elif isinstance(item, dict):
            mid = item.get("id") or item.get("name") or item.get("model")
            if not mid:
                continue
            out.append({"id": str(mid), "name": str(item.get("name") or mid)})

    # 去重 + 排序
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for m in sorted(out, key=lambda x: x["id"]):
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        deduped.append(m)
    return deduped


__all__ = ["discover_models", "ModelDiscoveryError", "DISCOVERY_TIMEOUT"]
