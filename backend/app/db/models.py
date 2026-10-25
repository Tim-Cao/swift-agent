"""ORM 模型定义。

v10 新增:agent / tool / provider / model 四张元数据表,
把「智能体市场」「工具管理」「模型管理」的配置从代码/硬编码挪到数据库。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _new_id() -> str:
    return uuid.uuid4().hex


class Session(Base):
    """会话表。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    title: Mapped[str] = mapped_column(String(255), default="新会话", nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # v10:会话可绑定一个 DB agent(agent_id);为空则走默认 supervisor。
    agent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """消息表。"""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="messages")


class Provider(Base):
    """模型提供商表(OpenAI 兼容端点)。"""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # 「提供商 ID」——用户自己起的短标识(小写 + 短横线),全局唯一。
    # 与内部主键 id 分开:主键是 uuid,不可读也不适合给用户填。
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 该提供商下被设为「默认」的模型 id(可为空)
    default_model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    models: Mapped[list["Model"]] = relationship(
        back_populates="provider",
        cascade="all, delete-orphan",
    )


class Model(Base):
    """模型表(由提供商 /models 接口发现,存下来做快照)。"""

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 全局默认模型(整个系统只有一个默认模型)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    provider: Mapped["Provider"] = relationship(back_populates="models")


class Tool(Base):
    """工具表。

    builtin=True 的记录来自项目内置工具(tools/builtin/ 下的模块),
    前端只读,不允许编辑;builtin=False 的记录来自用户上传的 zip 包。
    """

    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    # 工具调用名(传给 create_deep_agent 的 tools=[...]),全局唯一
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # 展示名(前端卡片标题)
    display_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 上传 zip 解压后的目录(相对 backend/ 的路径);builtin 工具为 None
    source_dir: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Agent(Base):
    """智能体表。

    v11:「没有内置 agent」——所有 agent 都是普通 DB 记录,可以在页面上
    随意增删改。

    配置分两份,存在两个 JSON 字段里:
      - ``draft_config``   草稿配置(编辑页正在编辑的那份)
      - ``published_config`` 发布配置(智能体市场对外暴露的那份)

    两份 config 都是 JSON 字符串,结构一致::

        {"system_prompt": "...", "tool_ids": ["<tool_id>", ...]}

    「管理」卡片展示草稿配置,「市场」卡片展示发布配置。

    层级:
      - parent_id 为空 → 顶层 agent(可以被会话绑定)
      - parent_id 非空 → 子 agent,作为父 agent 的 ``task`` 工具可调度项
        (运行时转成 deepagents 的 subagents= 参数)
    """

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 草稿配置 JSON:{"system_prompt": str, "tool_ids": list[str]}
    draft_config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # 发布配置 JSON:同 draft_config 结构
    published_config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # 已发布 = 在「智能体市场」可见;未发布只在「智能体管理」可见
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 父 agent id(自引用);为空表示顶层 agent
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # 全局默认 agent(会话未绑定 agent 时用它);整个系统只有一个
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    children: Mapped[list["Agent"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Agent.created_at",
    )
    parent: Mapped["Agent | None"] = relationship(
        back_populates="children",
        remote_side=[id],
    )


class MCPServer(Base):
    """MCP 服务端表。

    v11.3:MCP 配置从 ``.mcp.json`` 文件挪到数据库 —— 跟 agent / tool / provider
    一样,元数据统一在 DB 里,页面可管理。

    两种传输方式:
      - ``stdio``:     本地起一个子进程(command + args),最常见
      - ``streamable_http``: 连一个 HTTP 端点(url)

    ``config_json`` 存传输相关的其它字段(命令、参数、url、env 键名等),
    具体结构见 ``app/services/mcp_config.py``。
    """

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    # MCP 名称(给用户看,也是 .mcp.json 里的 key)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # 传输方式:stdio / streamable_http
    transport: Mapped[str] = mapped_column(String(32), nullable=False, default="stdio")
    # 传输相关的配置 JSON(command/args/url/env ...)
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # 该 server 提供的工具名(连接时抓一次,给页面显示)
    tool_names: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # 连接状态:unknown / connected / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    status_detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
