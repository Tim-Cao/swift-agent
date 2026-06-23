"""DeepAgents Supervisor 装配(@lru_cache 单例)。

state / runtime 设计(简化):
  - state_schema 不传 → 用 deepagents 默认 DeepAgentState
  - context_schema 不传 → ContextT = None(业务 context 留给后续自定义 middleware,
    通过 Runtime[Context] / ToolRuntime[Context] 访问;当前阶段不需)
  - checkpointer=InMemorySaver() → 启用 thread 级 state 持久化
    (state 由 deepagents 内部按 thread_id 自动维护,调用方不传 state)
  - store=InMemoryStore() → 跨 thread 长期记忆(deepagents 不兜底)
  - backend=FilesystemBackend(root_dir=UPLOAD_ROOT, virtual_mode=True)
    → 沙箱:agent 通过 deepagents 内置 ls/read/write/edit/grep/glob 工具
    访问的所有路径都被强制在 UPLOAD_ROOT(/tmp/swift-agent)之下,路径
    穿越 (`..` / `~` / 绝对路径跳出 root) 直接 ValueError 拒绝。
    virtual_mode=True 把真实 root 隐藏成虚拟路径,agent 看到的路径形如
    "/<sid>/csv/TX103T-RG008_DS.csv",无法拼出真实 /private/...。
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from app.core.config import get_settings
from app.supervisor.checkpointer import get_checkpointer
from app.supervisor.llm import build_chat_model
from app.supervisor.store import get_store

logger = logging.getLogger(__name__)

# 与 uploads.py / downloads.py 保持一致
UPLOAD_ROOT = Path("/tmp/swift-agent")


def _build_backend() -> FilesystemBackend:
    """构造 FilesystemBackend 沙箱(root = UPLOAD_ROOT, virtual_mode=True)。

    virtual_mode=True 时:
      - 所有路径被视为虚拟绝对路径(/foo)锚定到 root
      - 路径穿越 (`..` / `~`) 直接 ValueError
      - resolved 路径必须仍在 root 内,否则 ValueError
      - agent 看到的路径是虚拟形式(不泄漏真实 root)

    即使业务工具(unzip_archive / inspect_csv / write_excel)直接调
    Python 文件 I/O 绕过 backend,backend 仍然守住 LLM 通过
    deepagents 内置 ls/read/write/edit/grep/glob 工具访问的所有路径,
    这才是 LLM 幻觉路径的入口。
    """
    return FilesystemBackend(
        root_dir=UPLOAD_ROOT,
        virtual_mode=True,
        max_file_size_mb=100,  # 单文件上限 100MB
    )


def _build_agent() -> Any:
    settings = get_settings()
    llm = build_chat_model(settings.llm)

    # 拉取扩展内容
    from middlewares import ALL_MIDDLEWARES
    from skills import load_skills
    from subagents import ALL_SUBAGENTS

    # 触发工具注册(@tool 装饰器在 import 时执行;subagents 在 import 时调
    # get_tools([...]),所以注册必须在 ALL_SUBAGENTS 构造前完成)
    from tools import excel_pipeline  # noqa: F401

    skills = load_skills("skills")
    backend = _build_backend()
    logger.info(
        "Loaded %d subagents, %d skills, %d middlewares; backend=FilesystemBackend(root=%s, virtual=True)",
        len(ALL_SUBAGENTS),
        len(skills),
        len(ALL_MIDDLEWARES),
        UPLOAD_ROOT,
    )

    return create_deep_agent(
        model=llm,
        system_prompt=settings.supervisor_system_prompt,
        subagents=ALL_SUBAGENTS,
        skills=skills,
        middleware=ALL_MIDDLEWARES,
        # state_schema / context_schema 均不传(默认 DeepAgentState + ContextT=None)
        checkpointer=get_checkpointer(),
        store=get_store(),
        # 沙箱:LLM 通过 deepagents 内置文件工具访问的所有路径强制在
        # UPLOAD_ROOT 之下,阻止乱探 /etc/passwd 之类的目录
        backend=backend,
        # 调试开关:.env SUPERVISOR_DEBUG 控制;默认 true(开启 LangGraph 详细 trace)
        debug=settings.supervisor_debug,
    )


@lru_cache(maxsize=1)
def get_supervisor() -> Any:
    """单例 supervisor(进程内缓存,deepagents 强依赖)。"""
    return _build_agent()


def make_thread_config(thread_id: str) -> dict:
    """绑定 thread_id 用于 stateful 多轮对话。

    注意:state 数据不由调用方传入,而是由 deepagents 内部 checkpointer
    按 thread_id 自动维护;调用方只通过 config.configurable.thread_id 索引。
    """
    return {"configurable": {"thread_id": thread_id}}


__all__ = ["get_supervisor", "make_thread_config"]
