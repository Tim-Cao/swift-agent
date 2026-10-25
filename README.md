# swift-agent

> 基于 FastAPI + LangChain + DeepAgents 的多智能体对话平台,Vue3 + Element Plus 对话前端。
> 智能体 / 工具 / 模型元数据全部由数据库驱动,前端提供智能体市场、工具管理、模型管理页面。

---

## 项目概览

`swift-agent` 是一个本地优先(stateful multi-turn)的多智能体聊天工作台:

- **后端**:FastAPI + SQLAlchemy 2 异步 + SQLite,LangGraph `Pregel` 跑 deepagents 的 supervisor,流式 SSE 产出 token / tool_call / tool_result / file / done / error 六类事件;
- **前端**:Vue 3 + Pinia + Vite,Element Plus UI,Notion 风格设计令牌,marked + highlight.js + DOMPurify 渲染 markdown;
- **图标**:统一用 bootstrap-icons(`<i class="bi bi-xxx">`),不再用 `@element-plus/icons-vue`;
- **Excel 处理流水线**:用户上传自然语言指令 + zip(多 CSV),Supervisor 串行调度 Intake → RuleParser → DataProcessing → ExcelWriter 四个 subagent,自动产出规范美化 Excel;
- **持久化**:`InMemorySaver` 持有图 state(多轮对话),`InMemoryStore` 给跨 thread 长期记忆;业务库(SQLite `sessions` / `messages`)独立承担审计与展示;
- **元数据驱动(v11)**:智能体 / 工具 / 提供商 / 模型四类元数据存在数据库里,运行时按记录调 `create_deep_agent` 动态构建,不再有硬编码的 subagent 列表;
- **没有内置智能体(v11)**:所有智能体都是普通 DB 记录,可增删改。Excel 流水线的 5 个 agent 首次启动时播种成普通记录,之后完全由用户在页面上管理;
- **纯图标按钮(v11.1)**:所有新建 / 上传 / 发布 / 删除等操作按钮都改成无文字的圆形图标按钮(`IconButton.vue`),hover 显示 title 提示;
- **输入区重做(v11.1)**:对话输入区是一个盒子,textarea 在上、图标行在下,共用一条外边框;用户上传的文件显示在**消息气泡里**(落进 user 消息的 `meta.attachments`),刷新页面也不丢;
- **工具包拖拽上传(v11.2)**:上传 zip 的入口挪进「新建 / 编辑工具」弹窗,变成一块可拖拽的区域;编辑时拖进新 zip = 替换实现(工具 id / 名字不变,智能体上的绑定不失效);
- **MCP 管理页(v11.3)**:MCP 服务端的元数据落库,前端新增「MCP 管理」卡片页(3 列),字段是 MCP 名称 + 传输方式(`stdio` / `Streamable HTTP`),支持新增 / 编辑 / 删除 / 测试连接 / 重新装载;
- **菜单重排(v11.3)**:应用名改成「Swift Agent」,主菜单只剩「新对话 / 智能体市场」,四个管理页收进默认收缩的「更多」分组,历史会话区改名「最近」并挪到主菜单最下方;
- **卡片版式(v11.3)**:所有卡片左侧一个类型图标(占两行),右侧第一行是状态 tag、第二行是名称;智能体卡片不再在底部重复显示状态,工具卡片的「内置」tag 移到类型图标右侧;
- **气泡统一走 el-tooltip(v11.3)**:全站文字气泡 / hover 提示统一用 Element Plus 的 `el-tooltip`,不再用原生 `title`;
- **扩展点**:`backend/{tools, skills, middlewares}/` 三个目录,业务新增能力无需改动 `app/`。

---

## 管理页面(v10)

前端左侧导航在 v11.3 重排成:应用名「Swift Agent」→ 主菜单(**新对话 / 智能体市场**)→ **更多**(默认收缩,含四个管理页)→ **最近**(历史会话)。所有页面用同一套 Notion 风格卡片栅格(桌面三列,窄屏自动降列):

| 页面 | 路由 | 说明 |
|---|---|---|
| 新对话 | `#/chat` | 豆包 / DeepSeek 风格落地页,可选智能体;也复用为对话工作区 |
| 智能体市场 | `#/market` | 只显示**已发布**的智能体,卡片展示**发布配置**,点击卡片直接开新会话 |
| 智能体管理 | `#/agents` | 全部智能体,卡片展示**草稿配置**;点「编辑」图标进编辑页 |
| 智能体编辑 | `#/agents/new`、`#/agents/{id}` | 独立页面(非弹窗),左栏名称+提示词、右栏工具选择;「保存草稿」「发布」两个按钮 |
| 工具管理 | `#/tools` | 全部工具;项目内置工具只读,自己的工具可上传 zip 接入 |
| 模型管理 | `#/models` | 分「提供商」「模型」两个 tab;提供商可配置,模型通过提供商发现 |
| MCP 管理 | `#/mcp` | MCP 服务端卡片页;MCP 名称 + 传输方式,支持测试连接 / 重新装载 |

### 卡片版式(v11.3)

所有管理页共用 `CardGrid.vue` 的同一套版式:

```
┌──────────────────────────────────────┐
│ ┌──┐  [类型] [状态]        (🔍)(✏)(🗑) │
│ │📦 │                                  │
│ │   │  名称                            │
│ └──┘                                  │
│  描述文字                             │
│  底部 meta                            │
└──────────────────────────────────────┘
```

- 左侧是**类型图标**(智能体 `bi-robot` / 工具 `bi-tools` / 提供商 `bi-plug` / 模型 `bi-cpu` / MCP `bi-plug`),纵向**占两行**;
- 右侧第一行是 **类型 tag + 状态 tag**(如「智能体」「已发布」),第二行是**名称**;
- 类型 tag 固定在最左:智能体 → 工具 → 提供商 → 模型 → MCP,状态 tag 紧随其后;
- 智能体卡片底部**不再重复显示状态**;工具卡片的「内置 / 只读」tag 从底部移到**类型图标右侧**;
- 模型卡片没有「普通」tag(只有「默认」),底部不显示模型 id,只显示所属提供商。

### 智能体:草稿 / 发布双配置(v11)

智能体**没有内置概念**,全部是普通 DB 记录。一条记录用两个 JSON 字段存配置:

| 字段 | 内容 | 谁在读 |
|---|---|---|
| `draft_config` | `{"system_prompt": str, "tool_ids": [str]}` | 「智能体管理」页的卡片、编辑页回填 |
| `published_config` | 同上 | 「智能体市场」页的卡片 |

- **保存草稿**只写 `draft_config`,不动市场展示;
- **发布**把当前配置同时写进两份 config 并置 `published=True`,此时市场才看得到;
- **模型不在 agent 上**:运行时统一查 `models.is_default=True` 的那一条来构建 LLM;
- **描述字段已移除**:deepagents 的 subagent spec 需要 `description`,播种时把原描述放在 `system_prompt` 首行,运行时取首行当 description。

父子关系用 `parent_id` 自引用外键表达:`parent_id` 非空的记录在运行时转成 deepagents 的 `subagents=` 参数。Excel 流水线的 4 个子 agent 就是这样挂在 Supervisor 下面的。

编辑页布局(左右两栏):

```
┌──────────────────────────────────────────────────────┐
│ ← 编辑智能体                     (💾) (☁)              │
├───────────────────────────┬──────────────────────────┤
│ 名称                       │ 工具            (+)      │
│ [____________________]    │ ┌──────────────────────┐ │
│                           │ │ execute_pandas_code ✕ │ │
│ 提示词 (System Prompt)    │ │ write_excel        ✕ │ │
│ [                       ] │ └──────────────────────┘ │
│ [                       ] │                          │
└───────────────────────────┴──────────────────────────┘
```

(💾) 是「保存草稿」,(☁) 是「发布」,都是纯图标圆形按钮(hover 有 title 提示)。

「+」按钮弹出工具多选框,勾选后回填右栏列表。

### 图标按钮与输入区(v11.1)

**所有操作按钮都是纯图标圆形按钮**,不显示文字,靠 `title` 做 hover 提示。统一封装在 `frontend/src/components/IconButton.vue`:

| 属性 | 说明 |
|---|---|
| `icon` | bootstrap-icons 的类名,如 `bi-plus-lg` / `bi-trash` |
| `title` | hover 提示,同时作为 `aria-label`;v11.3 起提示**走 `el-tooltip`**(不再是原生 `title` 属性),同时把文案镜像到 `data-tip` 给检查脚本当选择器 |
| `variant` | `primary`(主色实心)/ `default`(描边)/ `danger`(危险)/ `ghost`(无边框) |
| `small` | 小尺寸(工具选择弹窗里的「+」) |
| `loading` | 显示旋转的 `bi-arrow-repeat` 并禁用 |

涉及新建、上传、发布、停用、删除、编辑、刷新、发现模型、设为默认、新建会话、删除会话等。

> **v11.3:全站气泡统一 `el-tooltip`。** 侧边栏折叠按钮、会话列表、对话输入区、轨迹页、卡片操作按钮的 hover 提示
> 全部改成 Element Plus 的 `el-tooltip`,样式统一。注意 `el-tooltip` 的触发元素必须是**单个根元素**,
> 所以原来是 `<i>` / `<span>` 的地方都包了一层。检查脚本里 `.icon-btn[title=…]` 的选择器也随之
> 改成 `.icon-btn[data-tip=…]`(原生 `title` 属性已经没有了)。

**对话输入区**是一个盒子,textarea 在上、图标行在下,两者**共用一条外边框**(`.composer-box` 只有一条 `border`,`.composer-bar` 只画一条 `border-top` 作为内部分隔线):

```
┌────────────────────────────────────────────┐
│ 输入消息,Enter 发送,Shift+Enter 换行        │
│                                            │
├────────────────────────────────────────────┤
│ (📎) (🌐) (💾)                    ( ↑ )    │
└────────────────────────────────────────────┘
```

- 📎 上传 zip 包(上传中显示转圈);
- 🌐 / 💾 联网搜索开关:选中态是 `primary` 变体;
- ↑ 发送(等价于 Enter);没有文字时禁用。

**上传的文件显示在消息气泡里**,不再堆在输入框旁边。流程:

1. 前端 `InputBar` 上传成功后把 `{name, size_bytes, csv_count}` 随消息一起 POST;
2. 后端 `ChatRequest.attachment` → `stream_chat(attachment=...)`,把描述写进 user 消息的 `meta_json`:`{"attachments": [{name, size_bytes, csv_count}]}`;
3. 前端 `stores/session.js` 读历史时按 `filename` / `name` 把 `meta.attachments` 拆成两堆:
   - 有 `filename` → `attachments`(AI 产出的结果文件,显示下载按钮);
   - 有 `name` 没有 `filename` → `uploads`(用户上传的文件,渲染成气泡里的文件卡)。

所以刷新页面后,文件卡依然在原气泡中。

> 注意:`[UPLOAD_DIR:...]` 前缀**只是给 LLM 看的**,不能落库——落库的必须是用户原话。后端在 `stream_chat` 内部拼前缀,API 层不再拼第二遍,否则消息正文会被前缀污染。

### 内置工具的归属

项目自带工具统一收在 `backend/tools/builtin/`(unzip / inspect_csv / execute_pandas_code / write_excel),启动时播种进 `tools` 表并标记 `builtin=True`——前端能看到,但**不允许编辑或删除**(后端也会返回 400 拦截)。

### 上传自己的工具

上传入口在**「工具管理 → 新建工具 / 编辑工具」弹窗里**,是一块可拖拽的区域
(拖进去或点「点击选择文件」),不再有独立的「上传 zip 包」按钮。编辑时拖进新 zip
等于**替换实现**:工具的 id 和名字不变,只换代码 —— 这样智能体上已有的工具绑定不会因为换了 zip 就失效。

后端流程:**解压 → import .py → 捕获其中 `register_tool()` 注册的工具 → 写 DB**。

```python
# my_tool.py
from langchain_core.tools import tool
from tools import register_tool

@tool
def greet(name: str) -> str:
    """打个招呼"""
    return f"你好,{name}"

register_tool("greet", greet, display_name="打招呼")
```

可选 `manifest.json` 覆盖显示名 / 描述:

```json
{
  "tools": {
    "greet": { "display_name": "打招呼", "description": "礼貌地打个招呼" }
  }
}
```

安全约束:解压防 zip slip 路径穿越,只落白名单后缀(`.py/.json/.md/.txt/.csv`),大小上限 50MB。**import 会执行任意代码**,仅适用于本地自用场景,不要暴露到公网。

替换实现时有两个硬约束(见 `tests/test_tool_package_replace.py`):

- zip 里注册的工具名必须和被替换的工具**一致**,否则 400,原工具不受影响;
- 内置工具(`builtin=True`)不允许替换 —— 它的代码在仓库里,400 拦截。

> `load_tool_package()` 的 `known_names` 参数就是为「替换」准备的:同名重新注册不会被
> 「本包是否注册了新工具」这个判断漏掉,否则替换会被误判成"没注册任何工具"。

### 模型与提供商

提供商是 OpenAI 兼容端点。保存后点「发现模型」,后端调 `{base_url}/models`(或 `{base_url}/v1/models`)拉取可用模型并快照进 `models` 表。全局只允许一个默认模型,可在「模型」tab 点卡片设置 / 取消。

新增 / 编辑提供商的弹窗有四个**必填**字段(前端 `el-form` 校验 + 后端校验):

| 字段 | 说明 |
|---|---|
| 提供商名称 | 展示名 |
| 提供商 ID | 唯一 slug,存 `providers.slug`(唯一索引 `ux_providers_slug`) |
| Base URL | OpenAI 兼容端点地址 |
| API 密钥 | 只以掩码回传,留空表示不修改 |

卡片上**不显示 API Key**,只显示「提供商 ID:{slug}」和 Base URL。

> **掩码不能被当成真 key 存回去。** 掩码保留前 4 位(`sk-a`),所以判断要靠
> 「中间是否含 `***`」(`_is_mask`),不能靠 `startswith("***")` —— 那种写法永远
> 不成立,会把掩码当新 key 存进 DB,把真 key 覆盖成 `sk-a**********89`,
> 之后所有请求都用一把废 key,表现为「鉴权失败」。
> `tests/test_provider_api_key.py` 专门盯这个。

> **「提供商 ID 填了但看不到」是旧进程的问题,不是保存逻辑的问题。** 卡片读的是
> `providers.slug` 字段,而这个字段是 v11.3 才加进表结构的。**已经跑着的后端进程
> 里 ORM 元数据是旧的**,`GET /api/providers` 返回的 payload 根本没有 `slug` 键,
> 前端自然渲染不出来。重启后端即可(改代码前后端都要重启,Python 不会热加载)。

### MCP 管理(v11.3)

MCP 服务端的元数据**存数据库**(`mcp_servers` 表),不再只读 `.mcp.json` 文件。前端「MCP 管理」页是 3 列卡片栅格,每张卡片两个关键字段:**MCP 名称** 和 **传输方式**。

| 传输方式 | 必填字段 | 说明 |
|---|---|---|
| `stdio` | 命令、参数、环境变量 | 本地起一个进程,按 stdio 协议通信 |
| `Streamable HTTP` | URL、请求头 | 通过 HTTP(S) 连远程 MCP 服务端 |

卡片上还显示连接状态(未连接 / 已连接 / 连接失败)和该服务端的工具数。操作:

- **测试连接**(`bi-plug`):真去连一次,把 `status` / `status_detail` / `tool_names` 回写 DB;
- **重新装载全部 MCP**:关掉现有 client 再按 DB 重建,并把每台服务端的状态写回 DB;
- **删除**:从 DB 删掉记录。

后端 API(`/api/mcp`):`GET` / `POST` / `PATCH /{id}` / `DELETE /{id}` / `POST /{id}/test` / `POST /reload`。

**装载时机与容错**:`init_mcp()` 优先读 DB 里 `enabled=True` 的记录;DB 里一条都没有时,
才回落到 `.mcp.json`。每台服务端**单独** `get_tools(server_name=…)`,一台连不上不影响其他台
(以前是一把梭,一台炸了整批工具都没了)。启动时会打印 `MCP loaded N tool(s) from M server(s)`。

**密钥不落库**:环境变量字段写的是 `${VAR}` 引用,连接时才从进程环境里解析出真实值。
`seed_mcp_servers()` 从 `.mcp.json` 播种时也做同样转换,默认播种 `minimax-coding-plan-mcp`。




---

## 目录结构

```
swift-agent/
├── backend/                       # 【后端】FastAPI 应用(独立 uv 项目)
│   ├── tools/                     # 工具注册中心
│   │   ├── builtin/               # 项目内置工具(unzip / inspect_csv / execute_pandas_code / write_excel)
│   │   ├── excel_pipeline.py      # 向后兼容的再导出(旧 import 路径)
│   │   └── __init__.py            # TOOLKIT / TOOL_META / register_tool
│   ├── skills/                    # 技能目录(空骨架,扫描 */SKILL.md)
│   ├── middlewares/               # 中间件(build_middlewares() 每次返回新实例)
│   ├── app/
│   │   ├── core/                  # 配置(Settings) / 生命周期 / MCP
│   │   │   └── config.py          # Pydantic Settings + @lru_cache
│   │   ├── api/
│   │   │   ├── deps.py            # FastAPI Depends(get_db)
│   │   │   └── routes/
│   │   │       ├── __init__.py    # api_router 聚合
│   │   │       ├── health.py
│   │   │       ├── sessions.py    # /api/sessions CRUD(含 agent_id 绑定)
│   │   │       ├── messages.py    # /api/sessions/{id}/messages
│   │   │       ├── chat.py        # /api/chat/stream (SSE)
│   │   │       ├── uploads.py     # POST /api/uploads (zip → 解压)
│   │   │       ├── downloads.py   # GET  /api/downloads/<sid>/<name>
│   │   │       ├── agents.py      # /api/agents CRUD + /market
│   │   │       ├── tools.py       # /api/tools CRUD + /upload(zip)
│   │   │       ├── models.py      # /api/providers + /api/models
│   │   │       └── mcp.py         # /api/mcp CRUD + test + reload
│   │   ├── db/                    # SQLAlchemy 异步 ORM + repository
│   │   │   ├── models.py          # Session / Message / Agent / Tool / Provider / Model / MCPServer
│   │   │   ├── catalog_repository.py  # agent / tool / provider / model / mcp 的 CRUD
│   │   │   ├── seed.py            # 启动时播种内置工具、agent 与 MCP 服务端
│   │   │   ├── seed_data/         # Excel 流水线的 agent 提示词种子(纯数据)
│   │   │   └── migrations.py      # 幂等加列 + agents 表重建迁移
│   │   ├── schemas/               # Pydantic 数据模型(catalog.py = v10 元数据)
│   │   ├── services/              # 业务逻辑(chat_service / agent_service / model_discovery / mcp_config)
│   │   ├── tools_loader.py        # zip 工具包:解压 → import → 捕获注册的工具
│   │   └── supervisor/
│   │       ├── llm.py             # build_chat_model
│   │       ├── checkpointer.py    # PERSISTENCE_CHECKPOINTER_BACKEND 工厂
│   │       ├── store.py           # PERSISTENCE_STORE_BACKEND 工厂
│   │       ├── thread.py          # make_thread_config(thread_id)
│   │       └── agent_runtime.py   # v11:按 DB 记录建 agent(LocalShellBackend)
│   ├── tests/                     # pytest(覆盖 subagents / tools / skills / SSE / uploads / e2e)
│   ├── data/                      # SQLite 数据文件(.gitkeep)
│   ├── .env.example               # 配置模板
│   ├── pyproject.toml
│   └── uv.lock
│
├── frontend/                      # Vue3 SPA(Vite + Element Plus)
│   ├── src/
│   │   ├── api/                   # http.js + sessions.js + chat.js + agents/tools/models/mcp.js
│   │   ├── stores/                # Pinia(session / chat)
│   │   ├── router/index.js        # 无依赖 hash 路由
│   │   ├── styles/notion.css      # Notion 设计令牌 + 全局基础样式
│   │   ├── main.js                # 引入 bootstrap-icons 字体
│   │   ├── components/            # AppShell / CardGrid / SessionList / ChatWindow / ToolPicker / IconButton / ...
│   │   └── views/                 # ChatView / MarketView / AgentsView / AgentEditorView / ToolsView / ModelsView / McpView
│   ├── scripts/                   # 浏览器渲染 / 交互流程检查(CDP)
│   ├── vite.config.js             # host 0.0.0.0 / port 5173 + /api 代理
│   └── package.json
│
├── scripts/                       # 启动脚本(在仓库根)
│   ├── run_backend.sh
│   ├── run_frontend.sh
│   └── verify-minimax.sh         # 探测 MINIMAX_API_KEY 是否可用
│
├── docs/
│   └── trajectory.md              # 轨迹视图实现文档(JSONL schema / 折叠算法 / 前后端)
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
        ├─ event: file       data: {"url": "...", "filename": "...", ...}  (如生成 Excel)
        └─ event: done       data: {"session_id":"..."}
```

---

## Excel 处理流水线

输入:**自然语言指令 + zip 压缩包(多 CSV)**
输出:规范美化的 `.xlsx` 结果文件(前端弹下载卡片)

```
[Browser]   拖拽 zip → InputBar
   └─ POST /api/uploads  (multipart)  →  { session_id, upload_dir, csv_files, ... }
[Browser]   输入指令 + 点发送
   └─ POST /api/chat/stream  body={ message, upload_dir }
        Supervisor LLM 串行调度 4 个 subagent:
          ① IntakeAgent          unzip + inspect_csv
          ② RuleParserAgent      NL → pandas 代码
          ③ DataProcessingAgent  execute_pandas_code(沙箱) → result.csv
          ④ ExcelWriterAgent     write_excel → /tmp/swift-agent/<sid>/result.xlsx
        SSE 流末尾追加 file 事件:{ url, filename, mime, size_bytes }
[Browser]   MessageBubble 渲染附件下载卡片 → window.location.href 触发下载
```

### 4 个 subagent(Excel 流水线的 4 条 DB 记录)

| Agent | 职责 | 工具 |
|---|---|---|
| **IntakeAgent** | 解压 zip + 解析所有 CSV 结构(字段 / 类型 / 缺失值 / 样例) | `unzip_archive`, `inspect_csv` |
| **RuleParserAgent** | 自然语言指令 → 可执行 pandas Python 代码 | `execute_pandas_code` |
| **DataProcessingAgent** | 执行规则代码,产出中间 result.csv | `execute_pandas_code` |
| **ExcelWriterAgent** | 把 result.csv 写成规范美化 Excel | `write_excel` |

> v11.2 起这些 agent 的名字**去掉了 `ExcelPipeline.` 前缀** —— 播种数据里写的是
> `Supervisor` / `IntakeAgent` / …(deepagents 不校验名字格式,前缀纯属噪音)。
> 已经跑过的库由 `_migrate_agent_names()` 幂等迁移:只改这 5 条 Excel 流水线的记录,
> 用户自建的 agent 名字不动;目标名已被占用就跳过(不覆盖用户建的同名 agent)。

`execute_pandas_code` 沙箱:AST 白名单(拒绝 `import` / `open` / `exec` / dunder 访问)+ 受限 `exec`(`SAFE_BUILTINS` + `pd` + 已加载的 DataFrame),LDC 生成的代码不能直接被用户输入污染。

### 串行调度

deepagents 0.6.11 不提供 subagent 间显式编排。Supervisor 由 `task` 工具 + LLM 自调度,**串行顺序由 Supervisor 的提示词写明**(现在写在 `agents` 表的 `draft_config.system_prompt` / `published_config.system_prompt` 里,不再是代码常量),失败 3 次后把错误整理成 Markdown 表格告诉用户。

---

## state / runtime 设计

LangGraph 的 **state** 与 **runtime context** 是两条正交线,本项目当前**只使用 state**(不传自定义 context_schema):

### 构建期(每次请求按 DB 记录装配,`agent_service.py`)

v11 起**没有进程内单例 agent**——每轮请求都按当前 DB 记录现场构建:

```python
# app/services/agent_service.py
agent_rec = await resolve_agent_for_session(db, session_id)   # 会话绑定 → 默认 agent
cfg     = parse_agent_config(agent_rec.published_config or agent_rec.draft_config)
tools   = await _tool_instances(db, cfg["tool_ids"])            # tool id → 工具实例
subags  = await build_subagent_specs(db, agent_rec)             # parent_id 子记录 → subagents=
model, provider = await resolve_model(db)                       # models.is_default=True

agent = build_agent(
    name=agent_rec.name,
    system_prompt=cfg["system_prompt"],
    tools=tools,
    subagents=subags,
    model=model, provider=provider,
    middleware=build_middlewares(),      # 每次新实例,避免跨 agent 串味
    checkpointer=get_checkpointer(),
    store=get_store(),
)
```

`build_agent` 内部调 deepagents 的 `create_deep_agent`,后端固定用
`LocalShellBackend(root_dir=UPLOAD_ROOT, virtual_mode=False)`(真实文件系统沙箱)。

会话没绑 agent → 用 `is_default=True` 的那条;也没有 → 退化成「无提示词的裸 agent」,
不会 500。

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
| `file` | `{"url": "...", "filename": "...", "mime": "...", "size_bytes": N}` | 当 `write_excel` tool_result 输出 `.xlsx` 路径时,`chat_service._detect_file_event` 解析后下发,前端弹下载卡 |
| `done` | `{"session_id": "..."}` | 流结束 |
| `error` | `{"message": "..."}` | 流异常 |

`on_chain_*` / `metadata` 等中间链路事件在 `chat_service._map_event` 中过滤,不下发。

前端 `frontend/src/api/chat.js` 已按上述 schema 解析(`\n\n` 分隔,`event:` / `data:` 解析,分发到 `onToken` / `onToolCall` / `onToolResult` / `onDone` / `onError`)。

---

## 轨迹与 Session 日志

后端在写消息库(SQLite)的同时,把同一轮对话的所有步骤追加到一份 **JSONL session log**;前端通过 ``GET /api/sessions/{id}/trajectory`` 拿到折叠好的结构化轨迹,在「轨迹」Tab 的双栏视图里渲染。

设计参考 `deepseek-harness` 的 session log / trajectory 双层抽象:
- **session log**:追加式 JSONL,首行是 ``SessionHeader``,后续是 ``{seq, time, type, data}`` 事件。是会话的**唯一可信源**(同款 ``session.jsonl`` 也用于调试回放)。
- **trajectory**:session log 之上的**只读投影**,不写盘,只把 JSONL 折叠成前端友好的 turns / steps / summary。

### 文件布局

```
backend/data/sessions/<session_id>/session.jsonl
```

每行一条 JSON:

```jsonl
{"type":"session","version":1,"id":"...","created_at":1700000000,"model":"gpt-4o-mini"}
{"seq":1,"time":...,"type":"turn_start","data":{"turn":0}}
{"seq":2,"time":...,"type":"user_message","data":{"content":"hi"}}
{"seq":3,"time":...,"type":"assistant_chunk","data":{"turn":0,"step":0,"delta":"你好"}}
{"seq":4,"time":...,"type":"tool_call","data":{"turn":0,"step":1,"call_id":"...","name":"ls","input":{...}}}
{"seq":5,"time":...,"type":"tool_result","data":{"turn":0,"step":1,"call_id":"...","name":"ls","output":"...","is_error":false}}
{"seq":6,"time":...,"type":"file_emitted","data":{"url":"...","filename":"...","size_bytes":1234}}
{"seq":7,"time":...,"type":"turn_end","data":{"turn":0,"reason":"normal"}}
{"seq":8,"time":...,"type":"session_end","data":{"reason":"normal"}}
```

### 事件词汇(精简版)

| type | data | 触发 |
|---|---|---|
| `session_start` | (写到 header 第一行) | writer.open() 一次性 |
| `turn_start` | `{turn: int}` | 一轮对话开始 |
| `user_message` | `{content: str}` | 用户消息落库后 |
| `assistant_chunk` | `{turn, step, delta}` | 每个 LLM token |
| `assistant_message` | `{turn, step, content, usage}` | `on_chat_model_end` 收尾(含 token_usage) |
| `tool_call` | `{turn, step, call_id, name, input}` | `on_tool_start`(不再静默) |
| `tool_result` | `{turn, step, call_id, name, output, is_error}` | `on_tool_end` |
| `file_emitted` | `{turn, url, filename, mime, size_bytes}` | `_detect_file_event` 命中时 |
| `turn_end` | `{turn, reason}` | 流结束(normal / error / aborted) |
| `session_end` | `{reason}` | 与 turn_end 同,但保留语义扩展空间 |

> 注:`tool_call` / `tool_result` 现在写日志但**不发 SSE**(前端契约保持不变,仍是 token / file / done / error 四类)。

### API

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/sessions/{id}/trajectory` | 返回折叠好的 ``Trajectory``(header + turns + steps + summary) |
| `GET` | `/api/sessions/{id}/log/export` | 下载原始 JSONL,响应头 `Content-Disposition: attachment; filename="session-<id>.jsonl"` |

会话不存在 → 404;会话存在但无 JSONL → `summary.empty = true` 的占位响应(前端空状态提示)。

### 前端入口

- `ChatWindow.vue` 顶部是 Tab 行(对话 / 轨迹),每个会话各自记住选中的 Tab;
- 轨迹 tab 是双栏布局(对齐 deepseek-harness 的 TrajectoryTable):
  - 左栏 = 会话元信息 + 扁平事件流(system prompt / user message / tool / assistant / file 拍扁成按时间排序的单行卡片,Turn N 角标标出轮次);
  - 右栏 = 点某一行才滑出的详情面板(默认不占地方);
- 轮询:轨迹 tab 可见时持续拉取(流式中 1.5s,空闲 5s),切走即停;后台轮询失败静默重试;
- 头部有"刷新"和"下载 JSONL"两个按钮,可触发原始日志导出。

更详细的实现说明见 [`docs/trajectory.md`](docs/trajectory.md)。

### 实现位置

| 关注点 | 文件 |
|---|---|
| 事件 schema | `backend/app/trajectory/schema.py` |
| 写盘 + fsync | `backend/app/trajectory/log_writer.py` |
| 读 + 折叠 | `backend/app/trajectory/log_reader.py` |
| SSE 流里挂日志 | `backend/app/services/chat_service.py`(`SessionLogWriter` + `_log_raw_event`) |
| API 路由 | `backend/app/api/routes/trajectory.py` |
| 前端 API wrapper | `frontend/src/api/trajectory.js` |
| 轨迹 UI | `frontend/src/components/TrajectoryView.vue` + `TrajectoryStepItem.vue` + `TrajectoryDetailsPanel.vue` |
| 单元 / 集成测试 | `backend/tests/test_trajectory.py`(20 cases,涵盖 writer / reader / API) |

### 配置

`backend/app/core/config.py` 暴露两个开关(都有默认值):

| 字段 | 默认 | 含义 |
|---|---|---|
| `trajectory_log_dir` | `./data/sessions` | session log 落盘根目录(每个 session 一个子目录) |
| `trajectory_log_enabled` | `True` | 总开关(`False` 时所有写入静默跳过) |

---

## 扩展指南

三个顶层目录 `tools/ skills/ middlewares/` 都是**空骨架**,新增能力只需注册,不改动 `app/`。
智能体不再需要代码目录——直接在页面上建,配置落 `agents` 表。

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

`agent_runtime.py` 用 `load_skills("skills")` 扫描目录。

### 新增智能体

v11 起**没有内置智能体**——agent 全部是普通 DB 记录,在前端「智能体管理」页
新建 / 编辑 / 发布,不用写代码。

想加一条带初始提示词的记录,往 `backend/app/db/seed_data/` 里加纯数据:

```python
# backend/app/db/seed_data/my_agent.py
SUPERVISOR = {
    "name": "Supervisor",
    "system_prompt": "你是 Supervisor,负责调度下面的子 agent……",
    "tool_names": [],                       # 工具注册名,播种时换算成 tool id
    "is_default": True,                     # 标记为默认 agent(全局只允许一个)
}
CHILDREN = [
    {
        "name": "WorkerAgent",
        "parent_name": "Supervisor",
        "system_prompt": "第一行是描述(运行时取首行当 deepagents 的 description)",
        "tool_names": ["execute_pandas_code"],
    },
]
```

再在 `backend/app/db/seed.py` 的 `seed_agents()` 里照 `excel_pipeline` 的写法播种。
播种**只在 `agents` 表为空时执行一次**,之后用户在页面上改的内容不会被启动流程覆盖。

### 运行时如何构建 agent

`backend/app/supervisor/agent_runtime.py` 是唯一的构建入口:

```python
LocalShellBackend(root_dir=UPLOAD_ROOT, virtual_mode=False)
```

`virtual_mode=False` 的语义:绝对路径原样使用(agent 看到 `/tmp/swift-agent/<sid>/csv/x.csv` 这种真实路径),相对路径相对 `root_dir` 解析,不做路径穿越拦截——本项目是本地自用工具,真正的边界由业务代码(`uploads` / `downloads` 的 session 归属校验)把守。

模型解析:agent 上不再存 `model_id`,统一取 `models` 表里 `is_default=True` 的那一条;
没有默认模型时回退 `settings.llm`。

### 新增中间件

中间件由 `backend/middlewares/__init__.py` 的 `build_middlewares()` 统一组装,
**每次调用返回新实例**(避免多个 agent 之间共享有状态中间件):

```python
# backend/middlewares/my_middleware.py
class MyMiddleware:
    async def __call__(self, ctx, call_next):
        # 前置逻辑(可读 runtime.context,需走 ToolRuntime[Context])
        result = await call_next()
        # 后置逻辑
        return result
```

```python
# backend/middlewares/__init__.py
def build_middlewares() -> list:
    return [
        WebSearchGateMiddleware(),
        MyMiddleware(),
    ]
```

---

## 配置

所有配置走 `backend/.env`,由 `app/core/config.py` 的 `pydantic_settings` 以 `@lru_cache` 缓存加载。前缀体系:

| 前缀 | 含义 | 字段 |
|---|---|---|
| `LLM_` | ChatOpenAI 模板 | `api_key` / `base_url` / `model` / `temperature` |
| `DB_` | 数据库 | `url` / `sql_echo` |
| `SERVER_` | HTTP 服务 | `host` / `port` / `cors_origins` |
| `APP_` | 应用聚合 | `app_name` / `supervisor_system_prompt` / `supervisor_debug` |
| `PERSISTENCE_` | LangGraph 持久化后端 | `checkpointer_backend` / `store_backend` / `checkpoint_db_url` / `store_db_url` |

`PERSISTENCE_*` 字段取值由 Pydantic `Literal["memory", "postgres"]` 约束;`memory` 是当前唯一完整实现,`postgres` 分支保留 `NotImplementedError`(未来接入 `langgraph-checkpoint-postgres` / `langgraph-store-postgres`)。

### `APP_SUPERVISOR_DEBUG`

`create_deep_agent(debug=)` 开关:`true` 时 LangGraph 打印每个 node / tool_call / state 转换的详细 trace,便于排查 subagent 调度;生产可设 `false` 减少日志噪音。默认 `true`。

---

## 测试

```bash
cd backend
uv run pytest -q
```

当前 215 个用例,**全部通过**。覆盖范围:`test_chat_sse` / `test_chat_file_event`(v8) /
`test_chat_stream_mapping`(v8.2) / `test_persistence_settings` / `test_middlewares` /
`test_skills` / `test_subagents`(原 + v7)/ `test_tools`(原 + v7)/ `test_backend_sandbox`(v8) /
`test_sessions_crud` / `test_uploads` / `test_excel_end_to_end` /
`test_user_attachment_persistence`(v11.1)/ `test_tool_package_replace`(v11.2)/
`test_mcp_crud`(v11.3)等。

> v10 时 `test_middlewares.py` 有两个用例因为全局 `ALL_MIDDLEWARES` 列表被跨用例污染而失败。
> v11 把全局列表换成 `build_middlewares()`(每次返回新实例)后已修复,现在全量跑是绿的。

### 前端检查

前端没有单元测试框架,用 CDP 驱动真实 Chrome 做检查(不开 `--no-sandbox`):

```bash
cd frontend
npm run dev                                    # :5173
node scripts/browser-check.mjs                 # 每个页面渲染 + 控制台错误
node scripts/flow-check.mjs                    # 新建 agent / 上传弹窗 / 提供商弹窗 / 圆形按钮 / 输入区
node scripts/upload-check.mjs  /tmp/testdata.zip  # 上传 → 文件卡进气泡
node scripts/upload-persist-check.mjs /tmp/testdata.zip  # 上传 → 刷新后文件卡仍在气泡里
node scripts/discover-check.mjs                 # 发现模型 → 列出提供商的可用模型
node scripts/new-chat-check.mjs                 # 新对话页 + 侧边栏重排
node scripts/screenshot.mjs                    # 截图到 /tmp/shots
node scripts/shot-w.mjs '#/chat' chat-wide 1440 900   # 指定尺寸截图
```

`browser-check.mjs` 与 `flow-check.mjs` 需要先起一个带远程调试端口的 Chrome:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --remote-debugging-port=9333 \
  --user-data-dir=/tmp/chrome-prof about:blank
```

> 检查脚本默认打 `http://127.0.0.1:5173`;要打到别的实例用 `CHECK_BASE=http://127.0.0.1:5174`。
> Vite 的代理目标可以用 `VITE_API_TARGET` 覆盖(默认 `http://localhost:8000`),
> 便于在不停掉旧后端的情况下起一套新后端 + 新前端做验证。

`browser-check.mjs` 与 `flow-check.mjs` 需要先起一个带远程调试端口的 Chrome:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --remote-debugging-port=9333 \
  --user-data-dir=/tmp/chrome-prof about:blank
```

### v8 新增

- `test_backend_sandbox.py`(7 用例):`create_deep_agent(backend=FilesystemBackend)` 沙箱,验证 `root_dir=/tmp/swift-agent` / `virtual_mode=True` 阻挡路径穿越;
- `test_chat_file_event.py`(6 用例):SSE `file` 事件检测,同时容忍 `/tmp` 与 `/private/tmp` 前缀(macOS symlink),拼出 `/api/downloads/<sid>/<filename>`;
- `test_chat_stream_mapping.py`(7 用例,v8.2):`on_chat_model_stream` 兼容 `AIMessageChunk.content` 的 `list[dict]` 形态(OpenAI 工具调用增量),只把 `type=='text'` 段拼成 token,纯 `tool_use` 段不发;
- 沙箱 import 策略简化:所有 import 一律 AST strip(沙箱 globals 已预加载 pd / np / math,LLM 写 `import os` 不再被拒);
- 前端 `MessageBubble.vue`:`fetch + Blob` 触发下载,带 downloading / done / error 状态反馈;
- 前端 `InputBar.vue`:上传触发从拖拽块改成 `el-button`(更醒目,符合用户习惯)。

### v11.1 新增

- `test_user_attachment_persistence.py`(3 用例):用户上传的文件落进 user 消息的 `meta_json.attachments`;不带附件的普通消息不写 meta;`[UPLOAD_DIR:...]` 前缀不落库(落库的必须是用户原话);
- 前端 `IconButton.vue`:纯图标圆形按钮封装(`icon` / `title` / `variant` / `small` / `loading`),替代所有带文字的操作按钮;
- 前端 `InputBar.vue` 重写:`.composer-box` 一条外边框包住 textarea + 底部 `.composer-bar` 图标行;
- 前端 `MessageBubble.vue`:新增 `uploads` prop,把用户上传的文件渲染成气泡里的文件卡;
- 前端 `stores/session.js`:`meta.attachments` 按 `filename` / `name` 拆成 `attachments`(AI 结果文件)和 `uploads`(用户上传文件);
- 后端 `ChatRequest.attachment` → `stream_chat(attachment=...)` → user 消息 `meta_json`;
- 后端 `app/api/routes/chat.py`:去掉重复拼 `[UPLOAD_DIR:...]` 的逻辑(前缀只由 `stream_chat` 内部拼一次);
- `test_provider_api_key.py`(8 用例):提供商的 API Key 掩码不能被当成新 key 存进 DB(修掉了 `startswith("***")` 那个永远不成立的判断);
- 术语统一:「供应商」→「提供商」(前端页面文案 + 后端注释/错误信息,API 路径和表名不变);
- 前端 `scripts/discover-check.mjs`:「发现模型」端到端检查(点放大镜 → 列出 minimax 的模型)。

### v11.2 新增

- 内置智能体名字去掉 `ExcelPipeline.` 前缀:播种数据(`app/db/seed_data/excel_pipeline.py`)+ 幂等数据迁移 `_migrate_agent_names()`(只改那 5 条,用户自建的同名 agent 不被覆盖);
- 后端 `POST /api/tools/upload` 支持 `replace_tool_id` / `display_name` / `description` 表单字段,新增 `_replace_tool_package()`:替换实现时保留工具 id 与名字,只换代码;
- 后端 `load_tool_package()` 新增 `known_names` 参数:同名重新注册也算「本包的工具」,否则替换会被误判成"没注册任何工具";
- 前端 `ToolEditor.vue` 重写:上传入口变成弹窗内的 `el-upload drag` 拖拽区(只收 `.zip`,最大 50MB),并带一个可折叠的「zip 包结构」说明;
- 前端 `api/tools.js`:`uploadToolPackage(file, opts)` 支持带 `replace_tool_id` 等字段;
- 前端 `ToolsView.vue`:删掉头部独立的「上传 zip 包」图标按钮;`ToolUploader.vue` 组件整个删除;
- `test_tool_package_replace.py`(5 用例):新建时前端显示名覆盖 / 替换保留 id 与名字 / 替换时沿用旧显示名 / 工具名不一致 → 400 / 内置工具不可替换;
- 前端 `scripts/flow-check.mjs` 第 3 节重写:断言工具页头部没有上传按钮、弹窗内有拖拽区、提示文案含「拖到这里」、`accept` 只收 `.zip`。

### v11.3 新增

**MCP 管理**

- 后端 `app/api/routes/mcp.py`(新):`GET/POST /api/mcp`、`PATCH/DELETE /api/mcp/{id}`、`POST /api/mcp/{id}/test`、`POST /api/mcp/reload`;响应里带 `transport_label` 和解析好的 `tool_names`;
- 后端 `app/services/mcp_config.py`(新):`TRANSPORTS`(`stdio` / `streamable_http`)、`TRANSPORT_LABELS`(`stdio` / `Streamable HTTP`)、`to_client_config` / `from_client_config`、`describe` / `parse_config` / `dump_config`、以及 `${ENV_NAME}` 解析;
- 后端 `app/db/models.py`:`MCPServer` 模型(名称、传输方式、配置 JSON、启用开关、状态 / 状态详情 / 工具名);
- 后端 `app/db/catalog_repository.py`:MCP 的 CRUD;
- 后端 `app/core/mcp.py` 重写:从 DB 读 enabled 的服务端(没有才回落 `.mcp.json`),**每台服务端单独** `get_tools(server_name=…)`,一台连不上不影响其他台,并把状态回写 DB;
- 后端 `app/db/seed.py`:`seed_mcp_servers()` 从 `.mcp.json` 播种(环境变量写成 `${VAR}` 引用,不落明文),默认播种 `minimax-coding-plan-mcp`;
- 前端 `src/api/mcp.js`(新)、`src/components/McpEditor.vue`(新,按传输方式切换字段)、`src/views/McpView.vue`(新,3 列卡片页);
- `test_mcp_crud.py`(11 用例):列表 / 新建、Streamable HTTP 传输方式、非法传输方式 → 400、重名 → 400、编辑 / 删除、404、以及配置翻译(`${VAR}` 解析、`describe`、`from_client_config`)。

**菜单与版式**

- 侧边栏:应用名 `swift-agent` → **Swift Agent**(图标与文字用 accent 色),「对话」→「新对话」,历史区「历史会话」→「**最近**」并挪到主菜单最下方,四个管理页收进默认收缩的「**更多**」分组(新增「MCP 管理」);
- 侧边栏收起/展开按钮从菜单栏移到**右侧主体区**左上角(`.collapse-btn` 绝对定位),收起后菜单只剩图标条(56px);
- `CardGrid.vue` 重排:类型图标**占两行**,右侧第一行状态、第二行名称;新增 `tags` 插槽;移除已无用的 `publishedOf` prop;
- 各页面加**类型 tag**:智能体 / 工具 / 提供商 / 模型 / MCP,位置在状态 tag 左侧;
- 智能体卡片:「取消发布」→「**停用**」(红色 `bi-power`),新增独立的**编辑**图标(`bi-pencil`),底部不再重复显示状态;
- 工具卡片:底部不再显示「内置 / 只读」,改到类型图标右侧显示 el-tag;
- 模型卡片:去掉「普通」tag,底部不显示模型 id(只显示所属提供商);
- 五个管理页去掉标题下面的描述文字。

**提示气泡**

- 全站 hover 提示统一改用 Element Plus 的 `el-tooltip`(侧边栏折叠按钮、会话列表、对话输入区、轨迹页、卡片操作按钮);
- `IconButton.vue` 修掉一个真 bug:模板里绑的是 `:content="tip"`,但 prop 名是 `title` —— 提示文字一直是空的。修好后把文案镜像到 `data-tip` 属性,检查脚本的选择器从 `.icon-btn[title=…]` 改成 `.icon-btn[data-tip=…]`;
- `providers` 表加 `slug` 字段:`ADD COLUMN ... NOT NULL DEFAULT ''` + 单独建唯一索引(不能直接 `ALTER TABLE ADD COLUMN` 一个 NOT NULL UNIQUE 列,也不能重建表——那会破坏 `models.provider_id` 的外键)。

---

## License

MIT