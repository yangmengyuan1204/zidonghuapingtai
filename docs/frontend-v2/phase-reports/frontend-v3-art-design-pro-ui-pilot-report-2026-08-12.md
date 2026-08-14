# Frontend V3 Art Design Pro UI Pilot — 验收报告（2026-08-12）

## 范围

- Pilot 1：全局 Shell
- Pilot 2：接口用例库
- 其它业务页面未主动修改；公共组件视觉影响自然扩散。

## 修改文件

- `frontend/src/components/AppShell.vue`（样式块重构）
- `frontend/src/views/ApiCasesView.vue`（纯展示结构 + 样式）
- `frontend/src/components/v2/base/BaseModal.vue`（关闭按钮/弹窗展示层）
- `frontend/src/components/AppFormDialog.vue`（textarea 全宽 + 展示层）
- `frontend/src/styles/v2/tokens.foundation.css`（新增 `--v2-layout-content-max: 1440px`）
- `frontend/src/styles/v2/tokens.component.css`（新增 `--v2-shell-pilot-*` token）
- `frontend/scripts/validate-v3-style-only-scope.mjs`（升级为 UI Pilot 业务不变校验）

## Template 修改内容

- `ApiCasesView.vue`：新增接口用例主操作移入 Page Header actions 槽；行操作区独立为 `v2-api-cases-row-actions`。
- `BaseModal.vue`：关闭按钮由文本 Close 改为 ×，aria-label 改为“关闭弹窗”。
- `AppFormDialog.vue`：textarea 字段追加全宽 class。
- `AppShell.vue`：模板与脚本未改。

## Style 修改内容

- Shell：白色侧栏 + 发丝边框、56px 顶栏、菜单分组/active 指示、用户区与 admin 链接精修、内容最大宽度 1440px、1080px 抽屉断点保留。
- 接口用例库：Page Header 去卡片化、Toolbar/Table/Pagination 融入单一内容卡片、表格固定布局 + 长文本截断、行高 45px、表头 38px、危险按钮改描边、分页底部化。
- Modal：640px 面板、紧凑关闭按钮、标题 16px。
- Form：JSON textarea 全宽 + 等宽字体。

## 公共组件修改

- `BaseModal` / `AppFormDialog` 仅展示层；props/emits/slots/v-model/行为未变。

## 业务逻辑变化

0。所有被修改 Vue 文件的 `<script>` 与 HEAD 逐字一致（由升级后的 scope validator 强制）；Router/Store/API/权限/字段/CRUD/批量/单条/分页/弹窗全部保留。

## 构建 / 校验 / 测试

- `npm run build`：PASS
- 23 个 validator：17 PASS / 6 FAIL（失败为基线既有的陈旧 V2 digest/allowlist 校验，与改动无关）
- `git diff --check`：PASS
- 浏览器冒烟：4 档宽度无横向溢出、Console error = 0、退出跳转 `/v3/login` 正常

## 浏览器视觉结果

- 1080 / 1240 / 1440 / 1920：无横向溢出；1080 为抽屉模式（触发按钮可用），≥1240 侧栏 220px。
- Sidebar 白色、Topbar 56px 白色；active 菜单为钴蓝文字 + 浅蓝底。
- Table：9 列齐全、行高 45px、表头 38px、Method/Status Badge 正常、操作区 4 个按钮单行不换行。
- Pagination：`共 82 条，第 1/5 页` + 7 个分页控件。
- 新增弹窗：640px、10 个字段、4 个 JSON textarea 全宽、取消/保存按钮在弹窗底部。
- 批量弹窗、全局 AI 配置弹窗正常打开/关闭。

## 截图位置

`docs/frontend-v2/ui-pilot-screenshots/`

- api-cases-1080.png / 1240 / 1440 / 1920
- sidebar-drawer-1080.png
- modal-create-1440.png / modal-batch-1440.png / modal-ai-config-1440.png

## Diff Audit

- 本次仅改上述 7 个文件 + 本报告/计划 + 截图目录。
- 未提交、未推送、未 merge；上一轮与其它任务未提交改动保持原样。

## 说明

- admin 权限已浏览器验证；normal 角色未在浏览器复测（无可用普通账号），其路由/权限由现有守卫与 validator 覆盖，源码未变。
- 6 个 V2 validator 为基线陈旧失败（与上一轮报告一致），未修改其保护对象去“绕过”。
