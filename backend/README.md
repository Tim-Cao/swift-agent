# swift-agent backend

FastAPI + LangChain + DeepAgents 多智能体后端。

## 启动

```bash
uv sync
cp .env.example .env        # 编辑填入 LLM_API_KEY
bash ../scripts/run_backend.sh
# 或: uv run uvicorn app.main:app --reload --port 8000
```

默认监听 `http://localhost:8000`,API 文档 `/docs`。

## 测试

```bash
uv run pytest -q
```

20 通过 / 1 v1 既有失败(`test_rename_first_user_message`)。详见根 README §测试。

## 目录

- `app/` — FastAPI 应用代码
  - `core/` — `config.py`(Pydantic Settings,`LLM_/DB_/SERVER_/APP_/PERSISTENCE_` 五类前缀)
  - `api/` — 路由聚合
    - `deps.py` — `Depends(get_db)`
    - `routes/` — `health` / `sessions` / `messages` / `chat`
  - `db/` — SQLAlchemy 2 异步 ORM + repository
  - `schemas/` — Pydantic 数据模型
  - `services/` — 业务逻辑(`chat_service` 事件映射 / `session_service`)
  - `supervisor/` — DeepAgents 装配
    - `llm.py` — `build_chat_model`
    - `checkpointer.py` — `PERSISTENCE_CHECKPOINTER_BACKEND` 工厂
    - `store.py` — `PERSISTENCE_STORE_BACKEND` 工厂
    - `builder.py` — `create_deep_agent` 单例装配 + `make_thread_config`
- `tools/` `skills/` `middlewares/` `subagents/` — 顶层扩展(空骨架,见根 README 扩展指南)
- `tests/` — pytest
- `data/` — SQLite 文件(.gitkeep)

## state / runtime 设计

详见根目录 README §state / runtime 设计。核心要点:

- `create_deep_agent(...)` 编译期注入 `checkpointer=InMemorySaver()` + `store=InMemoryStore()`;**不**传 `state_schema` / `context_schema`(用默认 `DeepAgentState` + `ContextT=None`)。
- `agent.astream_events(delta_input, config={"configurable": {"thread_id": session_id}}, version="v2")` 运行期只传**本轮 user message**(`delta_input = {"messages": [HumanMessage(content=user_message)]}`),历史由 `InMemorySaver` 还原,deepagents 的 `DeltaChannel._messages_delta_reducer` 按 `message.id` 去重合并。
- 业务库(SQLite)与 checkpointer 是两个独立层:业务库审计/展示,checkpointer 存图 state。

## License

MIT