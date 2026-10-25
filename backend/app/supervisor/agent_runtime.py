"""DB 驱动的 agent 运行时。

v11:agent 的元数据全部在数据库里(草稿 / 发布两份 JSON config),
运行时按记录调用 ``create_deep_agent`` 动态构建。

关键点:
  - **没有内置 agent**:Excel 流水线也是普通 DB 记录(见 app/db/seed.py)
  - 工具来自 ``tools.TOOLKIT``,按 config 里的 tool id 换成实例
  - backend 用 ``LocalShellBackend(virtual_mode=False)``:agent 看到真实路径
  - 模型:统一用「被标记为默认的模型」(models.is_default=True);
    没有默认模型时回落到 ``settings.llm``
  - 子 agent(``parent_id`` 非空)转成 deepagents 的 ``subagents=`` 参数
  - 已发布的 agent 用 published_config,未发布的用 draft_config
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.db.models import Model, Provider
from app.services.llm_payload import env_thinking_override, thinking_extra_body
from tools import get_tools

logger = logging.getLogger(__name__)

# 与 uploads.py / downloads.py 保持一致
UPLOAD_ROOT = Path("/tmp/swift-agent")


def build_backend() -> LocalShellBackend:
    """构造 LocalShellBackend(root=UPLOAD_ROOT, virtual_mode=False)。

    virtual_mode=False 的语义(见 deepagents 源码):
      - 绝对路径按原样使用(agent 看到 /tmp/swift-agent/<sid>/csv/xxx.csv 这种真实路径)
      - 相对路径相对 root_dir 解析
      - 不做路径穿越拦截 —— 本项目是本地自用工具,agent 需要能自由读写工作目录;
        真正的边界由业务代码(uploads/downloads 的 session 归属校验)把守。
    """
    return LocalShellBackend(root_dir=UPLOAD_ROOT, virtual_mode=False)


def build_chat_model_for(
    model: Model | None,
    provider: Provider | None,
) -> ChatOpenAI:
    """按模型 + 提供商构造 ChatOpenAI;无模型时回落到 settings.llm。

    ``extra_body`` 里的 MiniMax ``thinking`` 参数**按需**带(不是硬编码
    ``disabled``)—— 见 app/services/llm_payload.py:MiniMax-M3.1-Flash 强制要求
    ``adaptive``,传 ``disabled`` 会被服务端 400 拒掉。
    """
    settings = get_settings()
    if model is None or provider is None:
        llm = settings.llm
        return ChatOpenAI(
            model=llm.model,
            temperature=llm.temperature,
            api_key=llm.api_key,
            base_url=llm.base_url,
            extra_body=thinking_extra_body(
                model=llm.model,
                base_url=llm.base_url,
                override=env_thinking_override(),
            ),
        )

    return ChatOpenAI(
        model=model.id,
        temperature=settings.llm.temperature,
        api_key=provider.api_key,
        base_url=provider.base_url,
        extra_body=thinking_extra_body(
            model=model.id,
            base_url=provider.base_url,
            override=env_thinking_override(),
        ),
    )


def tools_for_ids(tool_ids: list[str]) -> list[Any]:
    """把 config 里的 tool id 列表换成工具实例(按 TOOLKIT 的注册名匹配)。

    tool id 与注册名一致 —— tools 表的主键就是注册名(见 app/db/seed.py:
    内置工具按 name 播种,id 由 uuid 生成)。这里同时接受两种写法:
    先按注册名找,找不到再按 id 查表(兼容上传工具的 uuid id)。
    """
    if not tool_ids:
        return []
    return get_tools(list(tool_ids))


def build_agent(
    *,
    name: str,
    system_prompt: str,
    tools: list[Any] | None = None,
    subagents: list[dict[str, Any]] | None = None,
    model: Model | None = None,
    provider: Provider | None = None,
    middleware: list[Any] | None = None,
    checkpointer: Any = None,
    store: Any = None,
    skills: list[str] | None = None,
    debug: bool | None = None,
) -> Any:
    """按解析好的配置构建 deepagents agent。"""
    settings = get_settings()
    llm = build_chat_model_for(model, provider)

    logger.info(
        "[agent] 构建 agent=%s tools=%d subagents=%d model=%s",
        name,
        len(tools or []),
        len(subagents or []),
        model.id if model else "(default)",
    )

    kwargs: dict[str, Any] = {
        "model": llm,
        "system_prompt": system_prompt or "",
        "backend": build_backend(),
        "debug": settings.supervisor_debug if debug is None else debug,
    }
    if tools:
        kwargs["tools"] = tools
    if middleware:
        kwargs["middleware"] = middleware
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    if store is not None:
        kwargs["store"] = store
    if skills:
        kwargs["skills"] = skills
    if subagents:
        kwargs["subagents"] = subagents

    return create_deep_agent(**kwargs)


__all__ = [
    "build_agent",
    "build_backend",
    "build_chat_model_for",
    "tools_for_ids",
    "UPLOAD_ROOT",
]
