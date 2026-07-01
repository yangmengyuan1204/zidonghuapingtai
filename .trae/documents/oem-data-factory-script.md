# OEM 数据工厂造数据脚本 — 实施计划

## 概要

为数据工厂新增 **OEM 站造数据脚本**。OEM 与日本站是**完全独立的两个项目**，业务流程、接口、节点都不同——本计划仅**参考日本站的脚本写法/代码风格**（步骤日志、接口调用、报告生成等模式），不复刻其流程。

OEM 实际造数据流程**节点很多**，用户口述的主线（创建订单→下单→后台报价→客户付款→后台发货）只是粗略概括，真实节点需在录制时逐个发现。因此本计划不预设脚本拆分，**录制完整流程后据实拆分**。

采用「用户操作浏览器 + 我后台录制 HAR + 逐节点确认」的方式抓取真实接口，再参照日本站脚本风格编写。

## 现状分析

- **OEM 零代码**：`app/` 与 `static/` 下无任何 OEM 相关实现。
- **日本站可复用资产**（`app/data_scripts.py`）：
  - 工具函数：`_step`（步骤记录）、`_post_admin_form`/`_post_admin_urlencoded`（后台接口调用+重试）、`_finish_named`（报告生成）、`_api_path`/`_api_paths`（路径可覆盖）。
  - 编排能力：`run_full_flow_script` 串联各独立脚本 + `_full_flow_record_step` 记录节点 + `_full_flow_finish` 收尾。
  - 登录：后台 `/admin.login` 返回 `access_token`；前台 `/client/userLogin` 返回 `userToken`。
- **站点配置机制**：`Env.base_url` + `global_vars`（存 `api_paths` 等动态变量），无独立 site_config 文件。日本站硬编码 `jpmanage.rakumart.cn`/`jpapi.rakumart.cn`，OEM 需参数化或独立 Env。
- **三层注册**：后端路由 `app/routers/data_scripts.py` + 前端 `BUILTIN_FLOW_DEFINITIONS`/`SCRIPT_PARAM_SCHEMAS`/`ensureXxxScript` 链。

## 执行方案

分四阶段，阶段一需用户配合操作，阶段二~四我独立完成。

---

### 阶段一：接口录制（需用户配合）

工具：`agent-browser`（基于 CDP，支持 HAR 录制 + 可见模式）。

OEM 节点很多，采用「分段录制 + 逐节点确认」策略：用户每操作完一个业务节点暂停，我抓取该节点产生的接口并记录节点名，确保每个接口都能对应到业务步骤。

**步骤：**
1. 用户提供 OEM 站前台 URL、后台 URL、前台帐号、后台帐号。
2. 我执行 `agent-browser --headed open <后台登录页>` 启动可见浏览器（用户可看到操作画面）。
3. 我代登录后台（或用户自行登录），确认登录成功。
4. 我执行 `agent-browser network har start` 开始录制全部网络请求。
5. **用户在浏览器中按 OEM 真实造数据流程操作**，每完成一个业务节点（如「选择客户」「加商品」「生成订单」「提交报价」…无论多细）就暂停，告诉我当前节点名。
6. 每个节点暂停时，我执行 `agent-browser network requests --method POST --type xhr,fetch` 查看该节点新增的 API 请求，再用 `agent-browser network request <requestId>` 读取完整 request/response（URL、方法、payload、响应体、状态码），并记录到「节点 → 接口清单」。
7. 用户继续下一节点，重复 5-6，直到整个造数据流程走完。
8. 全部节点走完后 `agent-browser network har stop ./oem_capture.har` 保存 HAR 存档备查。
9. 我整理出「节点名 → 接口路径 + 方法 + 参数 + 响应结构 + 鉴权方式」的完整 OEM 接口清单，作为阶段二拆分脚本的依据。

**产出：** OEM 完整流程接口清单（按业务节点分组：节点名/接口路径/方法/请求参数/响应字段/鉴权方式）。

> 节点很多时可分多次录制会话（每个会话走一段流程），最后合并接口清单。HAR 录制期间用户操作不受影响，我仅后台读取请求。

---

### 阶段二：脚本编写

文件：`app/data_scripts.py`（单文件追加，符合现有风格，每次改 1-2 个函数）。

**脚本拆分原则（录制后据实确定）：**
- 参照日本站「多个独立 `run_xxx_script` + 一个 `run_oem_full_flow_script` 编排串联」的结构。
- 按录制发现的业务节点边界拆分：把**强相关、常一起执行**的节点合并为一个脚本，把**可独立运行/可断点续跑**的节点拆为单独脚本。
- 具体拆成几个脚本、每个脚本包含哪些节点，**在阶段一录制完成后据实确定**，本阶段不预设函数名。
- 至少包含一个 `run_oem_full_flow_script` 全流程编排（参照 `run_full_flow_script` 的 `stop_after_node`/断点续跑机制）。

**编写规范（对齐日本站写法）：**
- 签名：`def run_oem_xxx_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]`
- 复用 `_step(log, name, payload, request, extra)` 记录每个节点。
- 复用 `_post_admin_form`/`_post_admin_urlencoded` 调后台接口（自带3次重试）。
- 复用 `_finish_named(SCRIPT_NAME, log, passed, summary)` 生成报告。
- API 路径走 `_api_path(variables, "oem_xxx", "/录制到的默认路径")`，OEM 路径差异通过 `variables["api_paths"]` 覆盖，保留多站点扩展能力。
- 鉴权：按录制结果确认 OEM 登录方式（后台 token / 前台 token 字段名可能与日本站不同），注入对应请求头。
- OEM 域名/Referer 等硬编码点改为 `variables.get("backend_manage_origin", "<oem默认>")` 形式，不写死日本站域名。

---

### 阶段三：后端路由 + 前端注册

**后端**（`app/routers/data_scripts.py`）：
- 按阶段二确定的每个 OEM 脚本，新增 `@router.post("/data-scripts/oem-xxx")` 路由，调用对应 `run_oem_xxx_script`，参照现有端点写法（`resolve_data_script_context` + `data_script_variables` + `save_record`）。
- 在 `app/main.py` import 区域补齐新函数名（如已 `from app.data_scripts import *` 则无需改）。

**前端**（`static/app.js`）：
- `BUILTIN_FLOW_DEFINITIONS` 新增每个 OEM 脚本条目（id/name）。
- `SCRIPT_PARAM_SCHEMAS` 新增各脚本参数表单（客户ID、商品关键词、店铺数、付款方式等，具体字段录制后据实补充）。
- 新增 `ensureOemXxxScript(...)` 并接入第42行附近的链式调用。
- 若 `openRunScriptForm`/`full-flow.js` 需要分发分支，按现有 `direct_box_to_shelf` 模式补充。

---

### 阶段四：站点配置

文件：`app/core/utils.py`。

- 新增 OEM Project（名称如「OEM站测试」）+ Env（`base_url` 指向 OEM 前台域名，`global_vars` 存 `api`/`backend_base_url`/`backend_manage_origin` 等）。
- 参照日本站初始化写法（`DATA_SCRIPT_PROJECT_NAME` 模式），增加 OEM 初始化分支（按 `project.name` 或独立标识判断）。
- 默认超时、登录账号等沿用 variables 覆盖机制。

## 需要用户提供的输入

执行阶段一前必须提供：
1. OEM 站前台 URL（如 `https://oemapi.xxx.com`）
2. OEM 站后台 URL（如 `https://oemmanage.xxx.com`）
3. 后台帐号 / 密码 / system / code（如 OEM 与日本站一致则说明）
4. 前台帐号 / 密码（客户帐号，用于下单/付款侧）

## 假设与决策

- **项目定位**：OEM 与日本站是独立项目，仅参考日本站脚本**写法**（步骤日志/接口调用/报告/编排模式），不复刻其流程与接口。
- **录制方式**：用户操作浏览器，我后台录制 HAR + 逐节点读取。这比「我自主探索」更准确，能抓到真实造数据流程的完整接口链；比「用户手填接口」更省用户精力。
- **脚本拆分**：不预设，录制完整流程后按实际节点边界据实拆分；至少一个 `run_oem_full_flow_script` 全流程编排（参照日本站 `run_full_flow_script` 的断点续跑机制）。
- **路径覆盖**：OEM 接口路径用 `_api_path` 机制，默认值取录制结果，可通过 `variables["api_paths"]` 整体覆盖，保留多站点扩展能力。
- **单文件追加**：所有 `run_oem_xxx_script` 写入 `app/data_scripts.py`，不新建模块，符合现有风格（每次改1-2个函数）。
- **不改动日本站逻辑**：OEM 为独立 Project/Env，不触碰日本站现有脚本与配置。

## 验证步骤

1. 录制完成后，对照 HAR 确认 OEM 完整流程各节点接口齐全、参数完整。
2. 脚本编写后，在数据工厂 UI 选择 OEM Project/Env，单独跑每个 `run_oem_xxx_script`，确认步骤日志含 request/row_count/summary。
3. 跑 `run_oem_full_flow_script` 端到端验证整个造数据链路通过。
4. 失败场景：人为构造某节点失败（如改错客户ID），确认错误信息清晰、流程可断点续跑（参照日本站 `resume_order_flow`）。
5. 报告产物：确认 `allure` 报告含每节点 request/响应摘要。
