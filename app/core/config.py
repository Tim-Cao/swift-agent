"""全局配置:pydantic_settings + @lru_cache。

所有配置从 .env 文件读取(字段前缀见下),由 get_settings() 入口暴露给应用。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """ChatOpenAI 固定模板参数(LLM_ 前缀)。"""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = ""
    base_url: str | None = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 60


class DatabaseSettings(BaseSettings):
    """数据库配置(DB_ 前缀)。"""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "sqlite+aiosqlite:///./data/app.db"
    sql_echo: bool = False


class ServerSettings(BaseSettings):
    """服务配置(SERVER_ 前缀)。"""

    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]


class AppSettings(BaseSettings):
    """应用聚合配置(无前缀)。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "swift-agent"
    supervisor_system_prompt: str = (
        "你是 Supervisor,把任务分派给最合适的子 Agent 处理。"
        "根据用户问题判断需要哪些能力,再聚合子 Agent 的结果给出最终答复。"
    )

    llm: LLMSettings = LLMSettings()
    db: DatabaseSettings = DatabaseSettings()
    server: ServerSettings = ServerSettings()


@lru_cache
def get_settings() -> AppSettings:
    """获取全局配置(进程内单例,@lru_cache 缓存)。"""
    return AppSettings()
