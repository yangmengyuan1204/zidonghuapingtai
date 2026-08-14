# Frontend V3 全系统功能指纹（修改前）

> 依据当前工作树真实源码扫描生成（`frontend/src`、`static`、`app` 只读）。

## 1. Shell（AppShell.vue）

- 菜单（4 组 / 9 项，顺序固定）：
  - 工作空间：工作台总览、项目空间
  - 测试资产：接口用例库
  - 自动化执行：数据工厂、需求验证中心、UI自动化、执行报告
  - 系统管理：系统回归、权限中心
- adminOnly：系统回归、权限中心（菜单与路由守卫双重）
- 当前项目选择：BaseSelect → `handleProjectChange` → `app.setProjectId` + `router.go(0)`
- 用户区：头像 / 用户名 / 角色 / 管理员·成员 Badge；admin 可见模板管理、自愈记录
- Topbar：全局 AI 配置（admin）、退出
- AI 配置弹窗：`AiConfigDialog`（admin，provider/base_url/model/api_key + 测试连接 + 保存）

## 2. 登录（LoginView.vue）

- 账号、密码、记住密码、登录；登录后按 redirect 回跳；无 adminOnly。

## 3. 工作台（DashboardView.vue）

- 指标：项目、环境、接口用例、UI 用例、执行记录 + QUALITY STATUS
- 趋势图、关注队列（失败待处理）、最近执行记录
- 表格列：ID / 类型 / 用例ID / 结果 / 执行时间 / 操作
- 操作：全部记录、查看执行报告、日志、截图、报告；项目筛选（全部项目）
- API：`getDashboard`、`listRecords`、`api` 客户端

## 4. 项目空间（ProjectsView.vue）

- 三个真实域：项目、环境、测试账号档案 + 项目默认账号绑定
- 项目列：ID / 项目名称 / 描述 / 默认测试账号 / 创建时间 / 操作
- 环境列：ID / 项目 / 环境名称 / Base URL / 超时 / 全局请求头 / 全局变量 / 操作
- 账号档案列：ID / 账号档案 / 范围 / 变量 / 状态 / 操作
- 按钮：新增项目、新增环境、新增测试账号、编辑、删除、账号（绑定）
- 权限：admin 可 CRUD，normal 只读；API：projects / envs / testAccounts

## 5. 接口用例库（ApiCasesView.vue）

- 筛选：项目、环境（环境随项目联动）
- 按钮：批量执行（无选择时 disabled）、新增接口用例（admin）、执行、复制（admin）、编辑（admin）、删除（admin）
- 表格列：Checkbox / ID / 项目 / 环境 / 用例名称 / 方法 / URL / 状态 / 操作
- Checkbox：`selectedIds` Set 多选
- 分页：pageSize=20，`共 X 条，第 Y/Z 页`
- Modal：新增/编辑/复制（10 字段：项目、环境、用例名称、请求方法、URL、请求头 JSON、参数 JSON、请求体、断言/提取 JSON、状态）；批量执行（运行时变量 JSON）
- API：listApiCases / updateApiCase / createApiCase / deleteApiCase / executeApiCase / batchExecuteApiCases / listEnvs

## 6. 数据工厂（legacy embed，DataScriptsView 承载）

- 脚本列表 active/hidden/deleted、脚本编辑、动态参数、录制、执行、结果
- Agent：目标理解、确认、风险、权限、取消、轮询
- 业务 JS 冻结：static/app.js、data-factory-agent.js、full-flow.js

## 7. 需求验证中心（RequirementVerificationView.vue）

- 筛选：搜索、项目（全部项目）
- 按钮：新建验证任务、创建任务、生成验证计划、分析、预检并执行、执行、暂停、继续、取消、删除任务、刷新
- 状态、轮询、错误、空态；Modal/表单；API：`verificationApi`

## 8. UI 自动化（UiCasesView.vue）

- 筛选：项目
- 按钮：新增UI用例、编辑、删除、录制UI用例、执行、查看记录、保存录制用例、返回录制、关闭、临时覆盖账号/验证码、统一账号相关选择
- 表格列：ID / 项目 / 用例名称 / 页面地址 / 超时 / 测试账号 / 状态 / 操作
- 录制/执行面板：步骤、定位器、动作、截图、变量提取、日志、轮询、进度、清理
- API：uiCasesApi、listTestAccounts、saveTestAccountBinding

## 9. 执行报告（RecordsView.vue）

- 筛选：项目、类型（api/ui/全部）
- 表格列：ID / 类型 / 用例ID / 结果 / 执行时间 / 操作
- 操作：再次执行（api/ui 条件控制）、日志、报告、截图；上一页/下一页
- API：`recordsApi`

## 10. 系统回归（legacy embed）

- adminOnly；分类、用例、参数、selection、保存、复制、重置、单条、批量、停止、重试、waiting_account、补账号继续、轮询、证据
- 业务 JS 冻结：static/system-regression.js

## 11. 权限中心（UsersView.vue）

- adminOnly 路由；表格列：ID / 账号 / 角色 / 创建时间 / 操作
- 按钮：新增用户、编辑、删除；字段：账号、密码、角色（仅 admin / normal）
- API：`usersApi`

## 12. 全局 AI 配置（AiConfigDialog.vue）

- 字段：服务类型、API 地址、模型、API Key（留空保留）
- 动作：读取配置、测试连接、保存配置；adminOnly

## 13. 模板管理 / 自愈记录（static/admin/*.html）

- 两个独立页面；模板：筛选、CRUD、步骤、测试运行、分页、展开、截图、确认、拒绝、撤销
- 自愈记录：筛选、记录详情；不合并

## 14. 全局

- 路由：`frontend/src/router/index.js` 全量保留（dashboard/projects/apiCases/dataScripts/requirementVerification/uiCases/records/systemRegression/users/login）
- Store：app / auth / toast / theme 全量保留
- 权限：`auth.isAdmin` / `adminOnly` / admin·normal 全量保留
