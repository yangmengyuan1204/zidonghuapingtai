# Frontend V2 Phase 5.5D.1 — Favicon Static Asset Hotfix

## Status

- Implementation: **PASS**
- Verification: **PASS**
- Phase 5.5D Implementation: **PASS**
- Phase 5.5D Verification: **PASS**
- PHASE 5.5D: **PASS**
- Date: 2026-07-30

本阶段只修复 favicon 静态资源合同，没有重新实施或调整 Phase 5.5D 的组件、业务或视觉迁移。

## Root Cause

- V2 两个 source HTML 原先均未声明 favicon，浏览器按默认行为请求绝对路径 `/favicon.ico`。
- FastAPI 原先没有 `/favicon.ico` 精确路由，请求落入 404 JSON 响应，因此全新浏览器上下文记录 Console Error。
- 仓库原先没有可复用 favicon 文件。
- Vite 5.4.21 的 `publicDir` 默认是 `frontend/public`：development 直接服务该目录，production build 将其复制到 `frontend/dist`。
- Vite 配置的全局 `base` 是 `/v3/`。Vite 在 production HTML transform 中会把 public asset `/favicon.ico` 改写为 `/v3/favicon.ico`，因此仅添加 source HTML link 仍不足以满足根路径合同。
- 实际启动 Vite standalone development server 后确认：其 base middleware 在 public middleware 之前处理请求，根 `/favicon.ico` 会稳定返回 404；仅依赖默认 publicDir 不能满足本阶段 development 合同。

## Git Baseline

- Branch: `codex/safe-refactor-preserve-features`
- HEAD: `a4c5764a759720707b34d65caddce7661d54e13d`
- Staged changes: none
- 开始前工作区已混有 Frontend V2、payment regression、backend、static 与 tests 等未提交改动；本阶段没有覆盖或处理这些改动。
- 未执行 `git add`、`reset`、`restore`、`checkout`、`clean`、`stash`、`commit` 或 `push`。

## Files Changed

创建：

- `frontend/public/favicon.ico`：唯一 source favicon，真实 ICO，32×32，766 bytes。
- `frontend/scripts/validate-v2-favicon-static-asset.mjs`：Phase 5.5D.1 RED → GREEN Validator。
- 本报告。

修改：

- `frontend/index.html`：显式声明 `/favicon.ico`。
- `frontend/dev/v2-base-components.html`：显式声明 `/favicon.ico`。
- `frontend/vite.config.js`：增加 favicon 专属 development middleware 与 production HTML post transform。
- `app/core/app_setup.py`：增加精确 GET `/favicon.ico` FileResponse。
- Phase 5.5D 报告：只更新解除 favicon 阻塞后的最终状态与验证记录。

未修改任何 Phase 5.5D 业务组件、Token、Router、Store、API、Permission、CRUD、Execute 或 Batch Execute 合同。

## RED / GREEN

RED 证据分两步取得：

1. Validator 创建后，因 source favicon、两个 HTML 引用、FastAPI 映射与 build artifact 全部缺失而失败。
2. 首次实现并 build 后，Validator 继续因 `frontend/dist/index.html` 将 href 改写成 `/v3/favicon.ico` 而失败：
   - `favicon href must be exactly /favicon.ico`
   - `HTML contains a forbidden favicon path`
   - `production HTML must preserve the absolute root favicon href`
3. 首次实际启动 Vite standalone development server 后，根 `/favicon.ico` 返回 404；将 development 精确映射合同加入 Validator 后，因共享 ICO 读取、精确 middleware、MIME 与 bytes 返回均缺失而 RED。

增加 Vite favicon 专属 hook 并重新 build 后，Validator GREEN。Self-check 可识别：缺失资源、错误 href、伪 ICO、错误 FastAPI 映射、dist `/v3/favicon.ico`、JS/CSS base 误伤、全局 base 修改与重复 favicon 声明。

## Vite Build URL Preservation

- 使用 Vite 5.4.21 正式公开的 `configureServer` 与 `transformIndexHtml` 插件钩子；本地 `vite/dist/node/index.d.ts` 明确声明这两个 hook 与 HTML post transform 顺序。
- development 侧只在 request URL 精确等于 `/favicon.ico` 时返回共享 ICO；其他请求立即交给既有 Vite middleware。
- production HTML transform 只处理同时满足以下条件的标签：`link`、`rel` 包含 `icon`、最终 href 精确等于 `/v3/favicon.ico`。
- hook 只把该标签的 href 恢复为 `/favicon.ico`；不会处理 script、stylesheet、图片、字体或其他 link。
- 未修改 `base`、`outDir`、input、assetsDir、publicDir、proxy、alias 或 Vue plugin 行为。
- Source HTML：`href="/favicon.ico"`；dist HTML：`href="/favicon.ico"`。
- dist 入口 JavaScript 与 CSS 仍分别使用 `/v3/assets/index-*.js` 和 `/v3/assets/index-*.css`，证明其他资源继续遵守 `/v3/` base。

## Vite Development Verification

实际临时启动 Vite 5.4.21 standalone server，并在验证后立即停止：

- `/v3/`：HTTP 200；source HTML 中 `/favicon.ico` 计数 1，`/v3/favicon.ico` 计数 0。
- `/favicon.ico`：HTTP 200、`image/vnd.microsoft.icon`、766 bytes。
- `/v3/@vite/client`：HTTP 200、`text/javascript`，证明 favicon middleware 没有截获其他开发资源。
- 没有修改 Vite 全局 base、proxy、publicDir 或其他开发服务器行为。

## FastAPI Static Contract

- 静态调用链：`app/main.py` → `configure_app(app)`。
- GitNexus 对 `configure_app` 的影响结果为 UNKNOWN；静态检查确认调用点唯一，没有因此扩大修改范围。
- `configure_app` 在既有 `/static` mount 与 V3 SPA 路由之外增加精确 GET `/favicon.ico`，返回同一个 `frontend/public/favicon.ico`。
- 返回：HTTP 200、`image/vnd.microsoft.icon`、766 bytes，非 HTML、非 JSON。
- 应用启动与 `/health` 正常；`/static/index.html` 仍为 200 HTML；`/v3/phase55d1-fallback-check` 仍由既有 SPA fallback 返回 200 HTML。
- 路由仍包含 `/v3/`、`/v3`、`/v3/{path:path}`；API 注册、Router 顺序和其他静态映射未修改。

## Build Artifact Proof

| Artifact | Size | SHA-256 |
|---|---:|---|
| `frontend/public/favicon.ico` | 766 bytes | `16175CAD5EC42D5E6667DA3C5022AD4BA61E5F72508B1B8DFF9C7399677B8B21` |
| `frontend/dist/favicon.ico` | 766 bytes | `16175CAD5EC42D5E6667DA3C5022AD4BA61E5F72508B1B8DFF9C7399677B8B21` |

文件头、ICO directory、DIB payload 与 source/dist 内容一致性均由 Validator 校验。没有创建第二份 source favicon，也没有使用 PNG 重命名、空文件、文本占位、data URL 或外部网络资源。

## Browser Verification

使用独立、全新的 headed Playwright CLI 浏览器上下文；没有复用登录状态，没有过滤 Console/Network 错误，也没有注入全局 no-cache header。真实账号完成登录后验证：

| Entry | Final page | Declared href | Browser Resource Timing URL | Status / Type / Size | Console E/W | Page Error |
|---|---|---|---|---|---:|---:|
| `/v3/login` | `/v3/login` | `/favicon.ico` | `/favicon.ico` | 200 / `image/vnd.microsoft.icon` / 766 | 0 / 0 | 0 |
| `/v3/` | `/v3/dashboard` | `/favicon.ico` | `/favicon.ico` | 200 / `image/vnd.microsoft.icon` / 766 | 0 / 0 | 0 |
| `/v3/api-cases` | `/v3/api-cases` | `/favicon.ico` | `/favicon.ico` | 200 / `image/vnd.microsoft.icon` / 766 | 0 / 0 | 0 |
| `/v3/api-cases` refresh | `/v3/api-cases` | `/favicon.ico` | `/favicon.ico` | 200 / `image/vnd.microsoft.icon` / 766 | 0 / 0 | 0 |
| `/v3/dev/v2-base-components.html` | same | `/favicon.ico` | `/favicon.ico` | 200 / `image/vnd.microsoft.icon` / 766 | 0 / 0 | 0 |
| legacy `/` | `/` | no explicit link | browser default `/favicon.ico` | 200 / `image/vnd.microsoft.icon` / 766 | 0 / 0 | 0 |

浏览器 Resource Timing 中所有 favicon URL 都是 `/favicon.ico`，没有 `/v3/favicon.ico` 请求。

直接记录 `/v3/favicon.ico` 的现有行为：HTTP 200、`image/x-icon`、766 bytes。原因是 production public artifact 已在 `dist`，既有 `/v3/{path:path}` 静态解析可访问该文件；它不是 source HTML 正式引用，浏览器未请求该路径，本阶段没有为它新增路由或第二份 source asset。

## Console Results

- Frontend V2：Console **0 Error / 0 Warning**，Page Error **0**。
- legacy `/`：Console **0 Error / 0 Warning**，Page Error **0**。
- 没有 Playwright Console ignore/filter、404 隐藏或 route workaround。

## Automated Verification

以下命令全部 PASS：

- `node frontend/scripts/validate-v2-foundation.mjs`
- `node frontend/scripts/validate-login-redirect.mjs`（9/9）
- `node frontend/scripts/validate-v2-base-components.mjs`
- `node frontend/scripts/validate-v2-support-components.mjs`
- `node frontend/scripts/validate-v2-dropdown.mjs`
- `node frontend/scripts/validate-v2-resource-foundation.mjs`
- `node frontend/scripts/validate-v2-api-cases-direct-mapping.mjs`
- `node frontend/scripts/validate-v2-api-cases-foundation-integration.mjs`
- `node frontend/scripts/validate-v2-favicon-static-asset.mjs`
- `npm --prefix frontend run build`（161 modules）
- `git diff --check`（无 whitespace error；仅工作区既有 LF/CRLF 提示）

## Legacy Isolation

- legacy `/` 的 HTML、Router 与静态入口未修改。
- legacy 继续通过原有 `/static` 资源路径运行。
- legacy 默认 favicon 请求现在由精确根路由返回真实 ICO；没有引入 Frontend V2 DOM、Token 或 Portal。

## Phase 5.5D Reverification

- Phase 5.5D 的全部既有 Validator 与 production build 再次 PASS。
- 全新浏览器上下文中的唯一阻塞 `/favicon.ico` 404 已消失。
- Phase 5.5D 业务接入文件由 favicon Validator 的固定 SHA-256 保护，未被本热修复修改。
- Phase 5.5D：Implementation **PASS**，Verification **PASS**，PHASE 5.5D **PASS**。

## Remaining Risks

- 工作区仍混有大量其他任务未提交改动，后续 Git 操作必须继续精确列文件，禁止整体暂存。
- `/v3/favicon.ico` 因既有 V3 dist 静态解析可直接访问，但没有任何正式 HTML 引用或浏览器请求；本阶段按批准要求只记录实际行为，不扩大静态路由修改。
- Vite favicon plugin 依赖公开插件 API；development 精确匹配根请求，production 匹配目标包含当前 `/v3/` build 输出。未来若 V2 base 合同改变，应同步审查该专属插件与 Validator，不能改成通用 URL 重写。

PHASE 5.5D.1 PASS
