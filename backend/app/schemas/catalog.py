"""v11 元数据 Pydantic 模型:Agent / Tool / Provider / Model。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------- Tool ----------


class ToolOut(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    builtin: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field("", max_length=128)
    description: str = ""


class ToolUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=128)
    description: str | None = None
    name: str | None = Field(None, min_length=1, max_length=128)


# ---------- Agent ----------


class AgentConfig(BaseModel):
    """agent 的配置体(存成 JSON 字段)。

    v11:提示词和绑定的工具都放在这里,草稿 / 发布各存一份。
    模型不在这里 —— 运行时统一用「被标记为默认的模型」。
    """

    system_prompt: str = ""
    tool_ids: list[str] = []


class AgentOut(BaseModel):
    id: str
    name: str
    # 草稿配置(管理页展示 / 编辑)
    draft_config: AgentConfig = Field(default_factory=AgentConfig)
    # 发布配置(市场展示)
    published_config: AgentConfig = Field(default_factory=AgentConfig)
    published: bool
    parent_id: str | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    draft_config: AgentConfig = Field(default_factory=AgentConfig)
    # 建时若给了 published_config,published 自动置 true
    published_config: AgentConfig | None = None
    parent_id: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    draft_config: AgentConfig | None = None
    published_config: AgentConfig | None = None
    published: bool | None = None
    parent_id: str | None = None


# ---------- Provider ----------


class ProviderOut(BaseModel):
    id: str
    name: str
    # 「提供商 ID」——用户自己起的短标识(小写 + 短横线),全局唯一
    slug: str = ""
    base_url: str
    api_key: str = ""
    enabled: bool
    default_model_id: str | None
    model_ids: list[str] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    # 提供商 ID:全局唯一,必填(后端仍会规整 + 去重)
    slug: str = Field(..., min_length=1, max_length=64)
    base_url: str = Field(..., min_length=1, max_length=512)
    # API 密钥:新增时必填(编辑时留空表示"不修改")
    api_key: str = Field(..., min_length=1)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    slug: str | None = Field(None, max_length=64)
    base_url: str | None = Field(None, min_length=1, max_length=512)
    api_key: str | None = None
    enabled: bool | None = None


# ---------- Model ----------


class ModelOut(BaseModel):
    id: str
    provider_id: str
    display_name: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ModelDiscoveryResult(BaseModel):
    """提供商 /models 接口的发现结果。"""

    provider_id: str
    models: list[str]
    added: int
    error: str | None = None


# ---------- MCP Server ----------


class MCPServerOut(BaseModel):
    id: str
    name: str
    # 传输方式:stdio / streamable_http
    transport: str
    # 传输方式的中文显示名(前端直接用)
    transport_label: str = ""
    # 传输相关配置(command/args/url/headers ...)
    config: dict[str, Any] = {}
    # 一行话描述(卡片用)
    description: str = ""
    tool_names: list[str] = []
    status: str = "unknown"
    status_detail: str = ""
    enabled: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    transport: str = Field(..., min_length=1, max_length=32)
    config: dict[str, Any] = {}
    enabled: bool = True


class MCPServerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    transport: str | None = Field(None, min_length=1, max_length=32)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
