# AGENTS.md — 接口 + UI 自动化测试平台

FastAPI + SQLite 测试平台：接口/UI 用例管理、数据脚本引擎、DeepSeek 数据智能体、需求校验。

## Project

- **Stack**: Python 3.11 (`.venv`), FastAPI 0.115, SQLAlchemy 2.0 + SQLite, Playwright 1.60
- **Entry**: `run_server.py` → `uvicorn app.main:app` (port 8000), 静态前端 `static/`
- **DB**: `auto_test_platform.db` (SQLite), 表定义在 `app/models.py`
- **Config**: 项目级 `reasonix.toml` (default_model=deepseek-flash), 全局 `~/reasonix/config.toml`
- **Windows 启动**: 双击 `启动服务.bat`（自动选 .venv python，杀旧端口，启动 uvicorn）

## Commands

```bash
# 启动开发服务器
python run_server.py --host 127.0.0.1 --port 8000

# 运行全部测试
.venv\Scripts\python.exe -m pytest tests/ -v

# 运行单个测试文件
.venv\Scripts\python.exe -m pytest tests/test_data_factory_agent.py -v

# 按关键字筛选
.venv\Scripts\python.exe -m pytest tests/ -v -k "agent"

# 安装依赖
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe -m playwright install
```

**测试必须用 `.venv\Scripts\python.exe`**（项目 venv Python 3.11），不能用系统 Python。

## Architecture

```
app/
├── main.py              # FastAPI app, CORS, 路由注册, 启动事件
├── models.py            # SQLAlchemy ORM (User,Project,Env,ApiCase,UiCase,TestRecord...)
├── schemas.py           # Pydantic 请求/响应模型
├── database.py          # SessionLocal, get_db 依赖
├── security.py          # JWT auth, require_admin 依赖
├── routers/             # API 路由 (auth, projects, api_cases, data_factory_agent, …)
├── services/            # 业务逻辑层
│   ├── data_factory_agent.py        # DeepSeek 数据智能体核心（目标理解→确认→执行循环）
│   ├── data_factory_agent_tools.py  # 智能体工具注册、执行、状态管理
│   ├── requirement_verification.py  # 需求校验引擎
│   └── verification_runtime_v2.py   # 校验运行时 v2
├── core/                # 基础设施
│   ├── utils.py         # save_record, 通用工具
│   ├── data_script_catalog.py  # 数据脚本注册表
│   ├── data_script_context.py  # data_script_variables()
│   └── constants.py     # 公共常量
├── data_scripts/        # 数据造数脚本（shopping_cart, full_flow, order_quote, payment...）
├── functional_testing/  # 功能测试引擎
│   └── model_client.py  # DeepSeek API 调用 + JSON 解析（call_local_model_json）
├── executors/           # 用例执行器
├── script_common/       # 脚本公共模块
├── oem_scripts/         # OEM 业务脚本
└── vendor/              # 第三方封装
```

**关键数据流**：用户自然语言 → `create_agent_session` → DeepSeek 目标理解 → 用户确认 → `_run_agent_session` 执行循环（每轮 `_next_agent_action` 调用 DeepSeek → `execute_agent_tool` 执行工具 → `_verify_goal` 校验）。

## Conventions

- 默认简体中文。新增代码保持项目现有风格，做最小改动。
- 后端路由 → `app/routers/`，业务逻辑 → `app/services/`，请求模型 → `app/schemas.py`
- 新前端 JS → `static/xxx.js`，不追加到 `static/app.js`
- 数据脚本只改当前目标脚本，不影响其他脚本的入参/返回值/执行流程。
- 修改前先 `git status --short`，只提交本次相关文件，不提交 `*.db`、`logs/`、`reports/`。
- 不允许 `git push --force`、`git reset --hard`、`git clean -fd`。

## Notes

- DeepSeek 数据智能体通过 `call_local_model_json` 调用 DeepSeek API，JSON 解析已做 4 层容错（尾随逗号、单引号、markdown 块、括号匹配）。
- 代理配置在全局 `config.toml` 的 `[network.proxy]`，类型 socks5。
- 执行记录存 `test_record` 表，`kind="data_agent"` 为智能体任务，`kind="data_agent_tool"` 为子工具调用。


## 核心规则

- 默认使用简体中文沟通、总结和说明。
- 修改代码前先理解现有逻辑，遵循最小改动原则，不做无关重构或批量格式化。
- 不覆盖用户已有改动，不擅自删除文件、清空文件或移除业务逻辑。
- 遇到需求不明确、业务风险较高、配置/依赖/架构变更时，先向用户确认。
- 配置文件、密钥、环境变量、构建配置等改动要特别谨慎，除非用户明确要求。
- 执行删除、强制覆盖、权限修改、全局安装等高风险命令前必须先确认。
- 新增代码保持项目现有风格，命名清晰，必要时补充简短注释。
- 修复问题时优先定位根因，做最小修复。
- 能自测的改动尽量自测；无法测试时说明原因和剩余风险。
- 编写新数据脚本时，不得影响已有脚本；所有改动限定在当前正在编写的脚本范围内，不修改其他脚本逻辑。
- 每次输出开头必须加上"你好老弟"。
- 遇到影响实现方向、数据安全、权限、数据库、配置的关键不确定点，必须先向用户反问确认，不允许猜测。

## 执行偏好

- 默认只做代码实现和必要测试，不做浏览器验证；除非用户明确要求，不启动/控制浏览器。
- 少输出 diff 和大段日志；需要检查改动时优先用 `git diff --stat`、定点 `rg`、语法检查和测试结果摘要。
- 读取大文件时只取相关函数/片段，避免整文件、超长行或宽泛搜索输出；`static/app.js` 这类大文件优先用定点脚本定位。
- 测试优先跑与改动相关的最小集合；必要时再跑完整测试，并只汇报通过/失败和关键错误。
- 过程说明保持简短，只汇报关键决策、阻塞点和最终结果；除非用户要求，不展开实现细节。
- 只输出需要修改的代码片段，不要解释。
- 不要重复完整文件。
- 新增功能、跨文件修改或风险较高改动前，先列出改动点并等用户确认；明确的小修复可直接改，改后汇报。
- 每次默认优先改 1-2 个核心文件；确实需要更多文件时，必须先说明原因。
- 优先给 diff patch 格式。
- 除固定开头“你好老弟”外，不添加其他问候语或过渡语，直接开始干活。
- 确认过的计划不再复述，直接按步骤执行。
- 报错只给关键行和修复方向，不贴完整堆栈。
- 已读过的文件用摘要引用（行号+关键句），不再重复全文。
- 构建/测试通过时只说"通过"，不贴输出。
- 列出多个方案时只给名称+一行对比，不要完整描述每个方案。
- 如果 `git push` 因大文件历史、网络超时等失败，按 `docs/git-push-troubleshooting.md` 排查；执行新建 worktree、迁移改动、改历史、强推前必须先停止并让用户确认。

## 项目维护与模块化规则

### 总目标

本项目后续所有修改都必须以“可维护、少污染、易回滚”为优先级。AI 不得为了快速实现需求而随意堆代码、创建临时文件、扩大大文件、改动无关逻辑。

### 修改前规则

- AI 开始修改前，必须先阅读当前需求相关文件，理解现有逻辑。
- 新增功能、跨文件修改或风险较高改动前，必须先列出预计修改的文件和每个文件的修改目的，等用户确认后再改；明确的小修复可直接改，改后汇报。
- 如果需求描述不清楚，必须先反问确认，不允许猜测实现。
- 如果发现已有未提交改动，必须说明，不允许覆盖、回退或提交无关改动。
- 每次优先只改 1-2 个核心文件；确实需要更多文件时，必须先说明原因。

### 模块化要求

- 新功能必须优先按业务模块新增或修改，不允许把所有代码都塞进一个文件。
- 后端接口代码优先放到 `app/routers/` 下对应业务路由文件。
- 后端业务逻辑优先放到 `app/services/` 下对应 service 文件。
- 数据模型只在确实需要新增数据库表或字段时修改 `app/models.py`。
- 请求/响应结构优先放到 `app/schemas.py`，复杂模块可以拆独立 schema 文件。
- 公共常量放到 `app/core/constants.py`，不要散落在多个文件里。
- 公共工具函数只有确实被多个模块复用时才允许抽取。
- 不允许继续把大量新逻辑堆进 `app/core/utils.py`。
- 前端新功能优先新增独立 JS 文件，例如 `static/xxx.js`。
- 不允许继续把大量新逻辑堆进 `static/app.js`。
- 如果必须修改大文件，只能做最小范围改动，并说明修改位置和原因。

### 文件管理规则

- 不允许在仓库中留下或提交无意义的临时文件、备份文件、调试文件、测试输出文件。
- 不允许留下 `tmp`、`bak`、`copy`、`new`、`debug`、`test123` 这类垃圾文件。
- 不允许随意新增文档、日志、截图、报告，除非用户明确要求。
- 不允许修改 `.secret_key`、数据库文件、环境配置、启动脚本，除非用户明确要求。
- 不允许删除文件、清空文件、批量移动文件，除非用户明确确认。
- 新增文件必须说明用途，并放到已有目录结构中合适的位置。

### 代码修改规则

- 遵循最小改动原则，只改和当前需求直接相关的代码。
- 不做无关重构、不批量格式化、不统一改风格。
- 保持项目现有命名、接口风格、返回格式和错误处理方式。
- 修改已有功能时，优先保持原有接口兼容。
- 涉及权限、登录、账号、数据库、执行流程、文件操作的改动必须先确认。
- 修复 bug 时必须先定位根因，再做最小修复。
- 不允许为了绕过错误而注释掉核心逻辑、权限校验或异常处理。

### 数据脚本规则

- 编写或修改数据脚本时，只允许改当前目标脚本。
- 不允许顺手修改其他已有脚本逻辑。
- 不允许影响已有脚本的入参、返回值和执行流程。
- 如果需要新增公共能力，必须先说明为什么不能只放在当前脚本中。

### 测试与验证规则

- 每次代码修改后，优先运行与改动相关的最小测试。
- 不要求默认启动浏览器验证，除非用户明确要求。
- 测试通过时只汇报“通过”。
- 测试失败时只汇报关键错误行和修复方向，不贴完整堆栈。
- 无法测试时必须说明原因和剩余风险。

### 用户提需求规则

- 用户可以直接用自然语言描述需求，不强制按固定模板填写。
- 如果用户只说一句话需求，AI 必须先阅读项目相关代码，再整理理解、影响范围和改动点。
- 如果信息不足，AI 必须反问确认，不允许自己猜。
- 用户不知道页面、接口、数据库、测试范围时，可以直接写“不知道”，由 AI 根据项目结构判断并说明。
- 下面模板只作为辅助，不是强制格式，AI 不得要求用户每次完整填写。

辅助模板：

```text
我想实现什么：
在哪个页面/功能里用：
期望效果：
不要影响哪些功能：
不清楚的地方写“不知道”：
```

## Git 小白安全规则

### 核心原则

- AI 每次改代码前必须先执行 `git status --short`。
- AI 不允许直接无脑执行 `git add -A`。
- AI 只能提交本次需求相关文件，不允许提交无关文件、数据库文件、日志文件、缓存文件、临时文件。
- 如果发现已有未提交改动，AI 必须说明哪些是已有改动，哪些是本次准备修改的文件。
- 如果无法判断某个改动是不是用户已有改动，必须先问用户。

### 不允许提交的文件类型

除非用户明确要求，AI 不允许提交这些文件：

```text
*.db
*.db-shm
*.db-wal
logs/
reports/
.ocr_cache/
.playwright-cli/
node_modules/
.venv/
.venv_ocr/
*.log
*.tmp
*.bak
*backup*
*copy*
debug*
test123*
```

### 提交前检查

每次修改完成后必须执行：

```bash
git status --short
git diff --stat
```

AI 必须先汇报：

```text
本次准备提交的文件：
- 文件1：修改原因
- 文件2：修改原因

不会提交的文件：
- 文件A：原因
```

### 提交规则

- 只允许添加本次需求相关文件，例如：

```bash
git add app/routers/xxx.py app/services/xxx.py tests/test_xxx.py
```

- 不允许默认使用：

```bash
git add -A
```

- 提交命令格式：

```bash
git commit -m "简短说明本次改动"
```

### 推送规则

- AI 默认不执行 `git push`。
- 只有用户明确说“推送”或“上传到远程”时，AI 才能执行推送。
- 推送前必须先执行：

```bash
git status --short
git branch --show-current
```

- 如果推送失败，按 `docs/git-push-troubleshooting.md` 排查，不允许乱删历史或强推。

### 禁止命令

除非用户明确要求并确认风险，AI 禁止执行：

```bash
git reset --hard
git checkout -- .
git clean -fd
git push --force
git rebase
```

### 小白友好说明

- AI 每次提交前必须用中文说明“要提交什么、不提交什么、为什么”。
- 如果用户不懂 Git，AI 不能要求用户自己判断复杂状态，必须给出推荐处理方式。
- 如果工作区有无关改动，AI 应该只提交本次相关文件，保留其他改动不动。
