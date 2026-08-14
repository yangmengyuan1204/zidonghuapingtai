# UI Prototype — 接口用例库（Art Design Pro 视觉结构复现）

## 用途

本目录是完全独立的静态 UI Prototype，用于视觉验收，**不进入生产项目**。

- 不引用 Vue 组件
- 不调用 API
- 不进入 Router / Store
- 不修改 `frontend/src`、`static`、后端或数据库

## 打开方式

直接双击 `index.html`，或在目录内启动静态服务器：

```powershell
cd D:\A_zidonghuapingtai\ui-prototype\api-cases-art-design
python -m http.server 8899
```

然后访问：

```text
http://127.0.0.1:8899/
```

## 文件

- `index.html` — Prototype 静态页面
- `styles.css` — 独立 Prototype Design Tokens 与视觉样式
- `BASELINE.txt` — 创建前的 Git 基线快照

## 业务内容来源（1:1）

- 菜单 / 分组 / 品牌 / 当前项目 / 用户区 / 管理入口：`frontend/src/components/AppShell.vue`
- 页面标题与说明、筛选（项目/环境）、批量执行、新增接口用例：`frontend/src/views/ApiCasesView.vue`
- 表格列（Checkbox / ID / 项目 / 环境 / 用例名称 / 方法 / URL / 状态 / 操作）：`frontend/src/views/ApiCasesView.vue`
- 操作（执行 / 复制 / 编辑 / 删除）：`frontend/src/views/ApiCasesView.vue`
- 表单字段（10 个）：`frontend/src/views/ApiCasesView.vue`

## 视觉结构来源（只读参考）

- `ui-reference/art-design-pro/src/components/core/layouts/art-page-content/index.vue`
- `ui-reference/art-design-pro/src/components/core/layouts/art-menus/art-sidebar-menu/`（index.vue / style.scss / theme.scss）
- `ui-reference/art-design-pro/src/components/core/layouts/art-header-bar/index.vue`
- `ui-reference/art-design-pro/src/components/core/layouts/art-breadcrumb/index.vue`
- `ui-reference/art-design-pro/src/components/core/forms/art-search-bar/index.vue`
- `ui-reference/art-design-pro/src/components/core/tables/art-table/`（index.vue / style.scss）
- `ui-reference/art-design-pro/src/components/core/tables/art-table-header/index.vue`
- `ui-reference/art-design-pro/src/views/system/role/modules/role-edit-dialog.vue`
- `ui-reference/art-design-pro/src/config/index.ts`（DESIGN 菜单主题、主色 #5D87FF）
- `ui-reference/art-design-pro/src/assets/styles/core/tailwind.css`（浅色主题变量）
- `ui-reference/art-design-pro/src/assets/styles/core/app.scss`（Card / Table Card 关系）

## 说明

- Prototype 无任何真实业务行为，仅为视觉样板。
- 对话框为静态 Visual Reference，展示真实存在的 10 个字段。
- 最终美丑由用户本人验收；验收通过后再单独制定生产迁移策略。
