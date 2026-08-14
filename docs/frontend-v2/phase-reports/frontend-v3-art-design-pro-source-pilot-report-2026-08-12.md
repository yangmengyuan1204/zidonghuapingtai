# Frontend V3 Art Design Pro 源码级 UI Pilot — 验收报告（2026-08-12）

## 1. Art Design Pro 源码依据（本地只读参考）

参考目录：`ui-reference/art-design-pro/`（HEAD `f3aaf58`，仅只读，未修改）。

### Shell / Layout

- `src/components/core/layouts/art-page-content/index.vue` — 页面容器 / 内容区
- `src/components/core/layouts/art-menus/art-sidebar-menu/index.vue` — 侧栏结构
- `src/components/core/layouts/art-menus/art-sidebar-menu/style.scss` — 侧栏布局数值
- `src/components/core/layouts/art-menus/art-sidebar-menu/theme.scss` — 菜单项 / active / hover 视觉
- `src/components/core/layouts/art-header-bar/index.vue` — 顶栏
- `src/components/core/layouts/art-breadcrumb/index.vue` — 面包屑
- `src/config/index.ts` — DESIGN 菜单主题（背景 `#FFFFFF`、文字 `#29343D`、图标 `#6B6B6B`）
- `src/assets/styles/core/tailwind.css` — `--art-gray-200: #f2f4f5`、`--art-card-border: rgba(0,0,0,.08)`、`--default-box-color: #ffffff`

### 接口用例库（CRUD 表格页面母版）

- `src/views/system/user/index.vue` — 页面容器 + 搜索卡 + 表格卡 + 新增 + 弹窗
- `src/views/system/role/index.vue` — 搜索卡 + 表格卡 + CRUD 动作 + 弹窗
- `src/components/core/forms/art-search-bar/index.vue` — 筛选/操作区
- `src/components/core/tables/art-table/index.vue` + `style.scss` — 表格容器与分页
- `src/components/core/tables/art-table-header/index.vue` — 表格卡头部
- `src/views/system/role/modules/role-edit-dialog.vue` — Dialog / Form footer 模式
- `src/assets/styles/core/app.scss` — Card / Table Card / 边框模式

## 2. Visual Mapping

| Art Design Pro 源码 | 当前项目映射 |
|---|---|
| `art-page-content` 内容容器 | `AppShell.vue` 的 `.v2-shell__content` |
| `art-sidebar-menu` + DESIGN 主题（白底 / 42px 菜单 / 6px 圆角 / active primary-light-9 + 4px 指示条） | `AppShell.vue` 的 `.v2-shell__sidebar` / `.v2-shell__nav-button` |
| `art-header-bar` + `art-breadcrumb` | `AppShell.vue` 的 `.v2-shell__topbar` / `.v2-shell__breadcrumb` |
| `user/index.vue` 页面层级（Page → 卡片 → Table → Dialog） | `ApiCasesView.vue` 的 Page Header → 内容卡 → Table → Pagination |
| `art-search-bar` 筛选/操作区 | `ApiCasesView.vue` 的 `.v2-api-cases-toolbar`（项目/环境 + 批量执行） |
| `art-table` + `art-table-card` | `ApiCasesView.vue` 的 `WorkbenchPanel` 内容卡 + `.v2-base-table` |
| `role/index.vue` 操作层级（主要/次级/危险） | 执行=primary，复制/编辑=secondary，删除=danger 描边 |
| `art-table` 内分页（bordered controls + active 填充） | `BasePagination` + `.v2-api-cases-pagination` |
| `role-edit-dialog.vue` Dialog/Form footer | `BaseModal` + `AppFormDialog`（640px、取消/保存） |

## 3. 修改文件

- `frontend/src/components/AppShell.vue`（样式块）
- `frontend/src/views/ApiCasesView.vue`（纯展示 template + 样式）
- `frontend/src/components/v2/base/BaseModal.vue`（展示层）
- `frontend/src/components/AppFormDialog.vue`（展示层）
- `frontend/src/styles/v2/tokens.foundation.css`（新增 `--v2-layout-menu-item-height`）
- `frontend/src/styles/v2/tokens.component.css`（新增 `--v2-shell-pilot-*` token）
- `frontend/scripts/validate-v3-style-only-scope.mjs`（升级为 UI Pilot 业务不变校验）

## 4. Template Changes

- `ApiCasesView.vue`：新增接口用例按钮移入 Page Header actions 槽（同一按钮、同一 `v-if="auth.isAdmin"` 与 `@click`）；行操作区类名改为 `v2-api-cases-row-actions`（纯 CSS 容器）。
- `BaseModal.vue`：关闭按钮文本改为 ×，`aria-label` 改为“关闭弹窗”。
- `AppFormDialog.vue`：textarea 字段追加全宽展示 class。
- `AppShell.vue`：template 未改。

## 5. Business Protection

- API：未改（`listApiCases` / `updateApiCase` / `createApiCase` / `deleteApiCase` / `executeApiCase` / `batchExecuteApiCases` / `listEnvs` 原样）
- Router：未改
- Store：未改
- 权限：未改（`auth.isAdmin` / `adminOnly` 原样）
- 字段：未改（10 个表单字段原样）
- 表格列：未改（9 列原样）
- 按钮：未改（批量执行/新增/执行/复制/编辑/删除 原样）
- CRUD / 执行 / payload：未改
- disabled / loading / empty / error：未改

## 6. Functional Fingerprint（前后对账）

| 项 | 修改前 | 修改后 | 结果 |
|---|---|---|---|
| Shell 菜单 | 9 项 / 4 组，顺序不变 | 9 项 / 4 组，顺序不变 | 一致 |
| adminOnly | users / systemRegression | 一致 | 一致 |
| 当前项目选择 / AI 配置 / 模板管理 / 自愈记录 / 退出 | 存在 | 存在 | 一致 |
| 筛选 | 项目 / 环境 | 项目 / 环境 | 一致 |
| 按钮 | 批量执行 / 新增 / 执行 / 复制 / 编辑 / 删除 | 同左 | 一致 |
| 表格列 | 9 列 | 9 列 | 一致 |
| Checkbox / 分页 / Modal | 原样 | 原样 | 一致 |
| 事件绑定 | 原样 | 原样 | 一致 |
| API 方法 | 原样 | 原样 | 一致 |

新增功能 = 0，删除功能 = 0，按钮/字段/列/筛选变化 = 0，API/权限/行为变化 = 0。

## 7. Build / Test

- `npm run build`：通过
- 23 个 validator：17 PASS / 6 FAIL（6 个为基线既有陈旧 V2 digest/allowlist 失败，与改动无关）
- `git diff --check`：通过
- 浏览器（1080 / 1240 / 1440 / 1920）：无横向溢出；Console error = 0；退出跳转 `/v3/login` 正常
- 结构实测：Sidebar 白底 220px（1080 抽屉 300px）、Topbar 56px、菜单项 42px / 圆角 6px、表头 38px、行高 45px、Modal 640px、4 个 JSON textarea 全宽

## 8. Git Diff

- `git status --short`：Pilot 修改文件如上；`ui-reference/`、截图、计划、报告为 untracked 保留；其它任务/V3 Light 未提交改动原样保留
- `git diff --stat`：6 个 Pilot 文件，684 insertions / 732 deletions（相对 HEAD 含 V3 Light 基线）
- 备份：`D:\A_zidonghuapingtai-pilot-before-art-design-pro.patch`（218,656 字节）
- `git diff --check`：0

## 9. Final Statement

本轮只完成 Shell + 接口用例库 UI Pilot。
未新增任何业务功能。
未删除任何业务功能。
未改变任何业务逻辑。
未修改后端。
未 commit。
未 push。
未 merge。
