"""全局配置:pydantic_settings + @lru_cache。

所有配置从 .env 文件读取(字段前缀见下),由 get_settings() 入口暴露给应用。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
    # max_tokens / timeout 已移除(以服务端默认为准)


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


class PersistenceSettings(BaseSettings):
    """LangGraph 持久化后端选择(PERSISTENCE_ 前缀,与 LangGraph 生态对齐)。

    checkpointer_backend: thread 级 state(checkpoint)后端
    store_backend:       跨 thread 长期记忆(store)后端
    当前实现仅 memory;postgres 分支在工厂函数中保留 NotImplementedError。
    checkpoint_db_url / store_db_url:留给未来 Postgres 实现连接串占位。
    """

    model_config = SettingsConfigDict(
        env_prefix="PERSISTENCE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    checkpointer_backend: Literal["memory", "postgres"] = "memory"
    store_backend: Literal["memory", "postgres"] = "memory"
    checkpoint_db_url: str | None = None
    store_db_url: str | None = None


class AppSettings(BaseSettings):
    """应用聚合配置(无前缀)。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "swift-agent"
    # create_deep_agent(debug=...) 开关:开启后 LangGraph 会打印每个 node /
    # tool call / state transition 的详细 trace。生产环境设为 false 减少噪音。
    supervisor_debug: bool = True
    supervisor_system_prompt: str = (
        "你是 swift-agent 的 Supervisor,中心调度器。你的职责:\n"
        "\n"
        "1. 接收用户的自然语言指令。消息里如果含 [UPLOAD_DIR:<path>] 标记,\n"
        "   说明用户上传了 zip 压缩包,应当触发 Excel 处理流水线。\n"
        "\n"
        "2. 提取用户提到的文件作为白名单。处理需求前先扫描用户消息,把消息里\n"
        "   显式提到的 .csv / .xlsx 文件名收集成 allowed_files(只保留这些,\n"
        "   不要把上传目录里其它文件塞进白名单)。例如:\n"
        "     - 用户说\"对比 a.csv 和 b.csv 的销量\" → allowed_files=[a.csv, b.csv]\n"
        "     - 用户说\"看一下 orders 文件\"          → allowed_files=[orders.csv] 等\n"
        "     - 用户没说具体文件                    → allowed_files=[]\n"
        "       这种情况 IntakeAgent 应当先返回全部 CSV 让用户选择,而不是擅自\n"
        "       把所有文件都加入白名单\n"
        "\n"
        "3. 若是 Excel 处理需求,严格按以下顺序串行调度子 Agent,\n"
        "   每步必须等待子 Agent 返回结果后才进入下一步:\n"
        "   ① IntakeAgent          - 解压 zip + 解析所有 CSV 结构\n"
        "     把 (csv_dir, allowed_files) 同时传给它,让它只 inspect 白名单里的\n"
        "     文件;白名单外文件不读取、不列举、不分析(隐私 + 性能)\n"
        "   ② RuleParserAgent      - 基于 IntakeAgent 返回的结构 + 自然语言\n"
        "     指令,生成 pandas 代码(只能引用 allowed_files 列出的 CSV)\n"
        "   ③ DataProcessingAgent  - 执行代码,产出 result.csv;\n"
        "     调用 execute_pandas_code 时**必须把 allowed_files 原样传下去**,\n"
        "     不允许扩大白名单、不允许删减白名单\n"
        "   ④ ExcelWriterAgent     - 写出规范美化 Excel,返回 output_path\n"
        "\n"
        "4. 每步异常(解压失败 / 规则解析失败 / 代码执行报错 / Excel 写入失败)时,\n"
        "   回到上一步重试;同一子 Agent 连续 3 次失败则把错误整理成 Markdown\n"
        "   表格告知用户,不再继续。\n"
        "\n"
        "5. ExcelWriterAgent 返回 {output_path, row_count, columns} 后,\n"
        "   把 output_path 用一句话告诉用户(下载链接由前端根据 session_id 拼)。\n"
        "\n"
        "6. 若用户消息不含 [UPLOAD_DIR:...] 标记,按普通对话回复(可调用通用\n"
        "   subagent / 工具,或直接回答)。\n"
        "\n"
        "禁止:\n"
        "- 跳过任何中间 subagent 直接调后置 subagent;\n"
        "- 同时并行调用多个 subagent(必须串行,等上一个返回);\n"
        "- 自己直接 import pandas / openpyxl / 写文件(只能通过 subagent);\n"
        "- 把 allowed_files 以外的 CSV 喂给 IntakeAgent / 沙箱;\n"
        "- 让 IntakeAgent 自行扫描 allowed_files 之外的文件。\n"
    )

    llm: LLMSettings = LLMSettings()
    db: DatabaseSettings = DatabaseSettings()
    server: ServerSettings = ServerSettings()
    persistence: PersistenceSettings = PersistenceSettings()


@lru_cache
def get_settings() -> AppSettings:
    """获取全局配置(进程内单例,@lru_cache 缓存)。"""
    return AppSettings()