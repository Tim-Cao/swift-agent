# swift-agent

> 基于 FastAPI + LangChain + DeepAgents 的多智能体对话平台,Vue3 + Element Plus 对话前端。

---

## 项目概览

`swift-agent` 是一个本地优先(stateful multi-turn)的多智能体聊天工作台:

- **后端**:FastAPI + SQLAlchemy 2 异步 + SQLite,LangGraph `Pregel` 跑 deepagents 的 supervisor,流式 SSE 产出 token / tool_call / tool_result / done / error 五类事件;
- **前端**:Vue 3 + Pinia + Vite,Element Plus UI,marked + highlight.js + DOMPurify 渲染 markdown;
- **持久化**:`InMemorySaver` 持有图 state(多轮对话),`InMemoryStore` 给跨 thread 长期记忆;业务库(SQLite `sessions` / `messages`)独立承担审计与展示;
- **扩展点**:`backend/{tools, skills, middlewares, subagents}/` 四个目录,业务新增能力无需改动 `app/`。

---

## 目录结构

```
swift-agent/
├── backend/                       # 【后端】FastAPI 应用(独立 uv 项目)
│   ├── tools/                     # 工具注册中心(空骨架,业务按需 register)
│   ├── skills/                    # 技能目录(空骨架,扫描 */SKILL.md)
│   ├── middlewares/               # 中间件(空骨架,ALL_MIDDLEWARES 列表)
│   ├── subagents/                 # 子 Agent(空骨架,ALL_SUBAGENTS 列表)
│   ├── app/
│   │   ├── core/                  # 配置(Settings) / 生命周期
│   │   │   └── config.py          # Pydantic Settings + @lru_cache
│   │   ├── api/
│   │   │   ├── deps.py            # FastAPI Depends(get_db)
│   │   │   └── routes/
│   │   │       ├── __init__.py    # api_router 聚合
│   │   │       ├── health.py
│   │   │       ├── sessions.py    # /api/sessions CRUD
│   │   │       ├── messages.py    # /api/sessions/{id}/messages
│   │   │       └── chat.py        # /api/chat/stream (SSE)
│   │   ├── db/                    # SQLAlchemy 异步 ORM + repository
│   │   ├── schemas/               # Pydantic 数据模型
│   │   ├── services/              # 业务逻辑(chat_service / session_service)
│   │   └── supervisor/
│   │       ├── llm.py             # build_chat_model
│   │       ├── checkpointer.py    # PERSISTENCE_CHECKPOINTER_BACKEND 工厂
│   │       ├── store.py           # PERSISTENCE_STORE_BACKEND 工厂
│   │       └── builder.py         # create_deep_agent 单例装配
│   ├── tests/                     # pytest(20 通过 + 1 v1 既有失败)
│   ├── data/                      # SQLite 数据文件(.gitkeep)
│   ├── .env.example               # 配置模板
│   ├── pyproject.toml
│   └── uv.lock
│
├── frontend/                      # Vue3 SPA(Vite + Element Plus)
│   ├── src/
│   │   ├── api/                   # http.js + sessions.js + chat.js(SSE 解析)
│   │   ├── stores/                # Pinia(session / chat)
│   │   ├── components/            # SessionList / ChatWindow / MessageBubble / ...
│   │   └── views/ChatView.vue     # 顶层布局
│   ├── vite.config.js             # host 0.0.0.0 / port 5173 + /api 代理
│   └── package.json
│
├── scripts/                       # 启动脚本(在仓库根)
│   ├── run_backend.sh
│   └── run_frontend.sh
│
├── .gitignore
└── README.md
```

---

## 快速开始

### 1. 后端(:8000)

```bash
cd backend
uv sync                                     # 依赖装在 backend/.venv
cp .env.example .env                        # 编辑,填入 LLM_API_KEY
bash ../scripts/run_backend.sh              # 或:uv run uvicorn app.main:app --reload --port 8000
```

API 文档:<http://localhost:8000/docs>。

### 2. 前端(:5173)

```bash
cd frontend
npm install
npm run dev
```

Vite 已配置 `/api` 代理到 `http://localhost:8000`,默认 `host: '0.0.0.0'` 允许同网段访问。

### 3. 一次对话的端到端流程

```
[Browser]   + 新建
   └─ POST /api/sessions → 200 { id: "<uuid>", title: "新会话", ... }
[Browser]   输入消息并发送
   └─ POST /api/chat/stream  (text/event-stream)
        ├─ event: token      data: {"content":"..."}
        ├─ event: tool_call  data: {"name":"...","input":{...}}   (如触发)
        ├─ event: tool_result data: {"name":"...","output":"..."}
        └─ event: done       data: {"session_id":"..."}
```

---

## state / runtime 设计

LangGraph 的 **state** 与 **runtime context** 是两条正交线,本项目当前**只使用 state**(不传自定义 context_schema):

### 编译期(进程启动时一次性装配,`builder.py`)

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model=llm,
    system_prompt=settings.supervisor_system_prompt,
    subagents=ALL_SUBAGENTS,        # list[dict]
    skills=skills,                  # list[str] skills/* 目录
    middleware=ALL_MIDDLEWARES,     # list(注意单数 middleware=)
    # state_schema / context_schema 都不传(默认 DeepAgentState + ContextT=None)
    checkpointer=get_checkpointer(),  # InMemorySaver (PERSISTENCE_CHECKPOINTER_BACKEND)
    store=get_store(),                # InMemoryStore  (PERSISTENCE_STORE_BACKEND)
)
```

`@lru_cache` 进程内单例。

### 运行期(`chat_service.stream_chat`)

```python
config = {"configurable": {"thread_id": session_id}}
delta_input = {"messages": [HumanMessage(content=user_message)]}

async for raw in agent.astream_events(delta_input, config=config, version="v2"):
    # 内部链:
    #   PregelLoop.__init__     → channels_from_checkpoint 还原历史
    #   _first()                → map_input(delta_input) → apply_writes
    #   DeltaChannel.update     → deepagents._messages_delta_reducer
    #                             (按 message.id 去重合并)
    ...
```

**关键**:`input` 是 **delta**——只传本轮新 user message,**不**传全量历史。LangGraph loop 启动时从 `InMemorySaver` 把 channel state 还原成历史 messages,然后 deepagents 的 `DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)` 按 `message.id` 去重合并新写入。传全量会让 `ensure_message_ids` 给老消息现场赋新 UUID,污染 checkpoint ID 链、扰乱 `PatchToolCallsMiddleware` / `SummarizationMiddleware` 的 tool_call ↔ tool_message 配对。

### 业务库 vs checkpointer

| 层 | 用途 | 存储 |
|---|---|---|
| **业务库** (SQLite) | 审计 / 展示 / 列表分页 | `sessions`、`messages` 表 |
| **checkpointer** (InMemorySaver) | LangGraph 图 state | 进程内存 |

两者通过 `session_id` 关联,内容独立。任何"读取对话历史"走业务库 (`repo.list_messages`);"恢复图执行状态"走 `agent.get_state(config)`(后续扩展)。

---

## 事件契约(SSE)

后端 `/api/chat/stream` 输出 `Content-Type: text/event-stream`,格式按 SSE 标准:

```
event: <type>
data: <json>
\n
```

| 事件 | data | 触发 |
|---|---|---|
| `token` | `{"content": "<incremental text>"}` | deepagents `on_chat_model_stream` chunk |
| `tool_call` | `{"name": "...", "input": {...}}` | deepagents `on_tool_start` |
| `tool_result` | `{"name": "...", "output": "..."}` | deepagents `on_tool_end`(output 兼容 ToolMessage / str / dict) |
| `done` | `{"session_id": "..."}` | 流结束 |
| `error` | `{"message": "..."}` | 流异常 |

`on_chain_*` / `metadata` 等中间链路事件在 `chat_service._map_event` 中过滤,不下发。

前端 `frontend/src/api/chat.js` 已按上述 schema 解析(`\n\n` 分隔,`event:` / `data:` 解析,分发到 `onToken` / `onToolCall` / `onToolResult` / `onDone` / `onError`)。

---

## 扩展指南

四个顶层目录 `tools/ skills/ middlewares/ subagents/` 都是**空骨架**,新增能力只需注册,不改动 `app/`。

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

`backend/skills/<name>/SKILL.md`(YAML frontmatter + 正文):

```markdown
---
name: my-skill
description: 技能描述
---

技能指令正文(交给 Agent 的具体行为说明)
```

`builder.py` 用 `load_skills("skills")` 扫描目录。

### 新增子 Agent

```python
# backend/subagents/my_subagent.py
my_agent = {
    "name": "MyAgent",
    "description": "Agent 描述",
    "system_prompt": "你是 ...",
    "tools": get_tools(["my_tool"]),   # 可选
    "skills": ["my-skill"],            # 可选
}
```

```python
# backend/subagents/__init__.py
from my_subagent import my_agent
from subagents import ALL_SUBAGENTS
ALL_SUBAGENTS.append(my_agent)
```

### 新增中间件

```python
# backend/middlewares/my_middleware.py
from middlewares import ALL_MIDDLEWARES

class MyMiddleware:
    async def __call__(self, ctx, call_next):
        # 前置逻辑(可读 runtime.context,需走 ToolRuntime[Context])
        result = await call_next()
        # 后置逻辑
        return result

ALL_MIDDLEWARES.append(MyMiddleware())
```

---

## 配置

所有配置走 `backend/.env`,由 `app/core/config.py` 的 `pydantic_settings` 以 `@lru_cache` 缓存加载。前缀体系:

| 前缀 | 含义 | 字段 |
|---|---|---|
| `LLM_` | ChatOpenAI 模板 | `api_key` / `base_url` / `model` / `temperature` |
| `DB_` | 数据库 | `url` / `sql_echo` |
| `SERVER_` | HTTP 服务 | `host` / `port` / `cors_origins` |
| `APP_` | 应用聚合 | `app_name` / `supervisor_system_prompt` |
| `PERSISTENCE_` | LangGraph 持久化后端 | `checkpointer_backend` / `store_backend` / `checkpoint_db_url` / `store_db_url` |

`PERSISTENCE_*` 字段取值由 Pydantic `Literal["memory", "postgres"]` 约束;`memory` 是当前唯一完整实现,`postgres` 分支保留 `NotImplementedError`(未来接入 `langgraph-checkpoint-postgres` / `langgraph-store-postgres`)。

---

## 测试

```bash
cd backend
uv run pytest -q
```

当前 20 通过 / 1 失败:

- ✅ `test_chat_sse` (3) — schema / supervisor config
- ✅ `test_persistence_settings` (5) — Literal 取值校验 + env override
- ✅ `test_middlewares` / `test_skills` / `test_subagents` / `test_tools` — 扩展注册
- ✅ `test_sessions_crud` — 部分用例
- ❌ `test_sessions_crud::test_rename_first_user_message` — v1 既有 bug,非本轮范围

---

## License

MIT