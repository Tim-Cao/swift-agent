# swift-agent backend

FastAPI + LangChain + DeepAgents 多智能体后端。

## 启动

```bash
uv sync
cp .env.example .env  # 编辑填入 LLM_API_KEY
bash scripts/run_backend.sh
# 或: uv run uvicorn app.main:app --reload --port 8000
```

默认监听 `http://localhost:8000`,API 文档 `/docs`。

## 测试

```bash
uv run pytest -q
```

## 目录

- `app/` — FastAPI 应用代码
- `tools/` `skills/` `middlewares/` `subagents/` — 顶层扩展(空骨架,见根 README 扩展指南)
- `tests/` — pytest
- `data/` — SQLite 文件(.gitkeep)
- `scripts/` — 启动脚本

## state / runtime

详见根目录 README 的 state / runtime 设计章节。核心要点:

- `create_deep_agent(...)` 编译期注入 `context_schema=AppContext` + `checkpointer=InMemorySaver()` + `store=InMemoryStore()`。
- `agent.stream_events(input, config={"configurable": {"thread_id": session_id}}, context=AppContext(...))` 运行期注入 thread_id 与业务上下文。

## License

MIT
