# Art Design Pro UI Pilot — 实施计划（2026-08-12）

## 范围

- Pilot 1：全局 Shell（`frontend/src/components/AppShell.vue` + Shell 相关 Design Token）
- Pilot 2：接口用例库（`frontend/src/views/ApiCasesView.vue` + 其直接依赖的公共展示组件）
- 其它业务页面不改。

## 视觉母版

- GitHub `Daymychen/art-design-pro`，仅作为布局/间距/表格/表单/弹窗/分页/设计语言参考。
- 不迁移其 Router/Store/权限/API/业务代码，不引入 Element Plus / Tailwind。

## 允许 / 禁止

- 允许：CSS、Design Token、Vue `<style>`、两个 Pilot 页面与指定公共组件的纯展示 `<template>` 结构。
- 禁止：改 API / Router / Store / Service / backend / database / payload / 权限 / 状态机 / 字段含义；禁止新增或删除功能入口。

## 改动文件

1. `frontend/src/components/AppShell.vue` — 样式块整体重构（浅色精致侧栏、56px 顶栏、内容最大宽度）。
2. `frontend/src/views/ApiCasesView.vue` — 页面层级重组 + 高密度表格视觉。
3. `frontend/src/components/v2/base/BaseModal.vue` — 关闭按钮与弹窗视觉精修。
4. `frontend/src/components/AppFormDialog.vue` — JSON textarea 全宽 + 等宽字体。
5. `frontend/src/styles/v2/tokens.foundation.css` / `tokens.component.css` — 追加 Pilot Token（不改旧值）。
6. `frontend/scripts/validate-v3-style-only-scope.mjs` — 升级为 UI Pilot 业务不变校验（script 与 HEAD 一致）。

## 验证

- `npm run build`
- 23 个 validator（预期 17 PASS / 6 个既有陈旧 V2 失败）
- 浏览器 1080 / 1240 / 1440 / 1920：Shell + 接口用例库 + 新增/批量/AI 配置弹窗
- 不 commit / push / merge
