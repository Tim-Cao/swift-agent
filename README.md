# swift-agent

> 基于 FastAPI + LangChain + DeepAgents 的多智能体对话平台,Vue3 + Element Plus 对话前端。

## 目录结构

```
swift-agent/
├── tools/              # 工具注册中心(空骨架,业务按需 register)
├── skills/             # 技能目录(空骨架,扫描 */SKILL.md)
├── middlewares/        # 中间件(空骨架,ALL_MIDDLEWARES 列表)
├── subagents/          # 子 Agent(空骨架,ALL_SUBAGENTS 列表)
├── app/                # FastAPI 应用
│   ├── core/           # 配置 / 日志 / 生命周期
│   ├── api/            # 路由
│   ├── db/             # SQLAlchemy 异步 ORM
│   ├── schemas/        # Pydantic 数据模型
│   ├── services/       # 业务逻辑
│   ├── supervisor/     # DeepAgents 装配
│   └── utils/          # 工具函数(暂空)
├── frontend/           # Vue3 SPA(Vite + Element Plus)
├── tests/              # pytest
└── scripts/            # 启动脚本
```

## 快速开始

### 1. 后端

```bash
# 安装依赖(需要 uv)
uv sync

# 复制并填写环境变量
cp .env.example .env
# 编辑 .env,填入 LLM_API_KEY

# 启动后端
bash scripts/run_backend.sh
# 或: uv run uvicorn app.main:app --reload --port 8000
```

后端默认监听 `http://localhost:8000`。

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://localhost:5173`,Vite 已配置 `/api` 代理到后端。

## 扩展指南

四个顶层目录 `tools/` `skills/` `middlewares/` `subagents/` 都是**空骨架**,新增能力只需注册,不改动 `app/`。

### 新增工具

```python
# 在你的业务模块中
from tools import register_tool
from langchain_core.tools import tool

@tool
def my_tool(q: str) -> str:
    """工具说明"""
    return "result"

register_tool("my_tool", my_tool)
```

### 新增 Skill

在 `skills/<name>/SKILL.md` 中:

```markdown
---
name: my-skill
description: 技能描述
---

技能指令正文(交给 Agent 的具体行为说明)
```

### 新增子 Agent

```python
# my_subagent.py
from tools import get_tools

my_agent = {
    "name": "MyAgent",
    "description": "Agent 描述",
    "system_prompt": "你是 ...",
    "tools": get_tools(["my_tool"]),
    "skills": ["my-skill"],
}
```

```python
# subagents/__init__.py
from my_pkg.my_subagent import my_agent
from subagents import ALL_SUBAGENTS
ALL_SUBAGENTS.append(my_agent)
```

### 新增中间件

```python
# my_middleware.py
from middlewares import Middleware, ALL_MIDDLEWARES

class MyMiddleware:
    async def __call__(self, ctx, call_next):
        # 前置逻辑
        result = await call_next()
        # 后置逻辑
        return result

ALL_MIDDLEWARES.append(MyMiddleware())
```

## 配置

全部配置走 `.env`,通过 `app/core/config.py` 的 `pydantic_settings` 加载,以 `@lru_cache` 缓存。

## License

MIT
