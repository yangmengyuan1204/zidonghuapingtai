# 安全审查报告

**审查范围**：`d:\A_zidonghuapingtai`（FastAPI 后端 + 原生 JS 前端）
**审查依据**：security-best-practices skill（FastAPI / 前端 JS 安全规范）
**审查日期**：2026-06-29

## 执行摘要

本次审查基于 FastAPI 后端与原生 JS 前端安全规范，共发现 **11 项** 安全问题，其中 **Critical 1 项、High 4 项、Medium 4 项、Low 2 项**。

最严重问题是任意已登录用户可通过 `/api/files/screenshot` 接口读取项目根目录下任意文件（包含 JWT 签名密钥 `.secret_key`），可借此伪造管理员 token 完全接管系统。**建议优先修复 SEC-01**。

---

## Critical

### SEC-01：`/api/files/screenshot` 任意文件读取（可窃取 JWT 密钥）

* **规则 ID**：FASTAPI-FILES-001 / FASTAPI-AUTHZ-001
* **严重度**：Critical
* **影响**：任意已登录用户（含普通子账号）可读取项目根目录下任意文件，包括 JWT 签名密钥 `.secret_key`、SQLite 数据库 `auto_test_platform.db`、可能的 `.env` 文件等，进而伪造 admin token 完全接管系统。
* **位置**：[app/main.py:1438-1440](file:///d:/A_zidonghuapingtai/app/main.py#L1438-L1440) + [app/core/utils.py:930-942](file:///d:/A_zidonghuapingtai/app/core/utils.py#L930-L942)
* **证据**：
  ```python
  @app.get("/api/files/screenshot")
  def get_screenshot_by_path(path: str = Query(...), current_user: User = Depends(get_current_user)) -> FileResponse:
      return safe_file_response(path)

  def safe_file_response(raw_path: str | None) -> FileResponse:
      ...
      resolved = file_path.resolve()
      base = BASE_DIR.resolve()
      if base not in resolved.parents and resolved != base:
          raise HTTPException(status_code=403, detail="禁止访问该文件")
      ...
      return FileResponse(resolved)
  ```
  `safe_file_response` 仅校验路径在 `BASE_DIR` 内，但未限定到截图目录。`current_user` 只要是已登录用户即可，无需 admin。
* **攻击路径**：`GET /api/files/screenshot?path=.secret_key` → 拿到 JWT 密钥 → 用密钥自签 `{"sub":"admin","exp":...}` → 以 admin 身份调用所有受保护接口。
* **修复建议**：将 `safe_file_response` 改为：1) 仅允许白名单目录（如 `reports/`、`FUNCTIONAL_SCREENSHOT_DIR`）；2) 或将 `get_screenshot_by_path` 限定为已记录的截图路径（从 DB 查 `TestRecord.screenshot` / `FunctionalScreenshot.image_path` 比对），不接受任意用户输入。
* **缓解**：临时方案——立即在反向代理层屏蔽 `/api/files/screenshot`，或要求 admin 权限。

---

## High

### SEC-02：CORS 配置过宽（`allow_methods/allow_headers=["*"]` + `allow_credentials=True`）

* **规则 ID**：FASTAPI-CORS-001
* **严重度**：Medium-High（origin 已 allowlist，否则为 High）
* **位置**：[app/main.py:251-257](file:///d:/A_zidonghuapingtai/app/main.py#L251-L257)
* **证据**：
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=allowed_origins,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
* **影响**：虽然 origin 不是 `*`，但 `allow_methods=["*"]` + `allow_headers=["*"]` 让任意允许的源可发起所有方法、携带任意头（含 `Authorization`）的跨域请求；若后续 `CORS_ORIGINS` 误配置为通配，会升级为高危。
* **修复**：
  ```python
  allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
  allow_headers=["Authorization", "Content-Type", "Accept"],
  ```

### SEC-03：OpenAPI 文档接口未关闭/未保护

* **规则 ID**：FASTAPI-OPENAPI-001
* **严重度**：Medium（敏感内部应用可视为 High）
* **位置**：[app/main.py:245](file:///d:/A_zidonghuapingtai/app/main.py#L245)
* **证据**：`app = FastAPI(title="接口 + UI 自动化测试平台", lifespan=lifespan)` 未设置 `docs_url=None, redoc_url=None, openapi_url=None`。
* **影响**：`/docs`、`/redoc`、`/openapi.json` 公开可访问，向匿名用户暴露全部 API 路由、参数 schema、模型字段，便于攻击者枚举接口。
* **修复**：生产环境关闭或加依赖保护：
  ```python
  app = FastAPI(
      title="接口 + UI 自动化测试平台",
      lifespan=lifespan,
      docs_url=None if os.getenv("ENV") == "prod" else "/docs",
      redoc_url=None if os.getenv("ENV") == "prod" else "/redoc",
      openapi_url=None if os.getenv("ENV") == "prod" else "/openapi.json",
  )
  ```

### SEC-04：前端在 localStorage 存储 JWT token + 明文密码（base64 仅混淆）

* **规则 ID**：JS-STORAGE-001
* **严重度**：High
* **位置**：[static/app.js:1, 19](file:///d:/A_zidonghuapingtai/static/app.js#L1)
* **证据**：
  ```javascript
  state.token = localStorage.getItem("token") || "";
  ...
  localStorage.setItem("token", state.token);
  ...
  // "记住密码"功能
  localStorage.setItem("savedPassword", btoa(form.get("password")));
  ```
* **影响**：1) JWT 存 localStorage，任何 XSS 可直接窃取 token 长期冒充用户；2) "记住密码"用 `btoa` 仅做 base64 编码（非加密），任何 XSS 或本机其他脚本可直接 `atob` 还原明文密码。配合 SEC-06（无 CSP + 多处 innerHTML）攻击面很大。
* **修复**：
  * token 改为后端 `HttpOnly` + `Secure` + `SameSite=Lax` Cookie（前端不再持有明文 token，CSRF 用 SameSite + 自定义头双保险）。
  * 移除"记住密码"功能，或改为后端下发长期 refresh token（HttpOnly Cookie），前端只存"是否记住"的布尔值。

### SEC-05：上传文件无大小限制（内存 DoS）

* **规则 ID**：FASTAPI-LIMITS-001 / FASTAPI-UPLOAD-001
* **严重度**：Medium-High
* **位置**：[app/routers/functional_tasks.py:526, 549, 582](file:///d:/A_zidonghuapingtai/app/routers/functional_tasks.py#L526), [app/routers/case_generation.py:96, 290](file:///d:/A_zidonghuapingtai/app/routers/case_generation.py#L96)
* **证据**：所有上传端点直接 `content = await file.read()` 一次性读入内存，无 `MAX_UPLOAD_SIZE` 校验。
* **影响**：admin 用户上传超大文件可耗尽内存（admin 可信但仍防误操作/被劫持账号）；批量上传端点 `files: list[UploadFile]` 风险更大。
* **修复**：读取前校验 `file.size` 或分块读取并累计：
  ```python
  MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
  content = await file.read()
  if len(content) > MAX_UPLOAD_BYTES:
      raise HTTPException(413, "文件过大")
  ```

---

## Medium

### SEC-06：前端大量使用 `innerHTML` 插入 API 返回数据（存储型 XSS 风险）

* **规则 ID**：JS-XSS-001
* **严重度**：Medium-High（依赖 SEC-04 的 token 泄露放大）
* **位置**：[static/admin/templates.html:259, 261, 322](file:///d:/A_zidonghuapingtai/static/admin/templates.html#L259), [static/app.js:382, 490](file:///d:/A_zidonghuapingtai/static/app.js#L382), [static/case-generation.js:100, 341, 490, 543](file:///d:/A_zidonghuapingtai/static/case-generation.js#L100), [static/full-flow.js:790](file:///d:/A_zidonghuapingtai/static/full-flow.js#L790), [static/test-status.js:132, 141, 155, 172, 193, 202](file:///d:/A_zidonghuapingtai/static/test-status.js#L132)
* **证据（典型）**：
  ```javascript
  // templates.html:259  p.name 未转义直接插入
  sel.innerHTML = '<option value="">全部</option>' + projects.map(p => `<option value="${p.id}">${p.name}</option>`).join("");
  ```
  `p.name` 来自数据库（用户可创建项目时命名），若包含 `<img src=x onerror=...>` 即触发存储型 XSS。
* **影响**：项目名/用例名/模板名等用户可控字段未转义直接拼到 innerHTML → 存储型 XSS → 配合 SEC-04 可窃取 JWT。
* **修复**：所有 `${p.name}` 等动态字段统一包 `escapeHtml(...)`；优先用 `textContent` / `createElement`。

### SEC-07：未部署 Content-Security-Policy

* **规则 ID**：JS-CSP-001
* **严重度**：Medium
* **位置**：全站无 CSP（header 或 `<meta>` 均无）
* **影响**：XSS 无纵深防御；配合 SEC-06 任意 XSS 可直接执行任意脚本。
* **修复**：在 FastAPI 添加中间件或反向代理层下发：
  ```
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'
  ```
  先用 `Content-Security-Policy-Report-Only` 观察一段时间再切换强制模式。

### SEC-08：Axure 文件上传无内容校验、无大小限制

* **规则 ID**：FASTAPI-UPLOAD-001
* **严重度**：Medium
* **位置**：[app/functional_testing.py:64-69](file:///d:/A_zidonghuapingtai/app/functional_testing.py#L64-L69)
* **证据**：
  ```python
  def store_axure_file(filename: str, content: bytes) -> str:
      ensure_functional_dirs()
      suffix = Path(filename or "prototype.rp").suffix or ".rp"
      target = AXURE_DIR / f"{uuid4()}{suffix}"
      target.write_bytes(content)
      return str(target)
  ```
* **影响**：1) 后缀直接取自用户上传文件名，可上传 `.html`/`.svg`/`.js` 等可执行内容；2) 无大小限制；3) 无内容类型校验（对比截图上传有魔数校验）。
* **修复**：白名单后缀 `[".rp", ".rplib", ".zip"]`；加 `MAX_UPLOAD_BYTES` 校验；如保留 `.html` 等需以 `Content-Disposition: attachment` 提供下载而非 inline。

### SEC-09：缺少安全响应头

* **规则 ID**：FASTAPI-HEADERS-001
* **严重度**：Medium
* **位置**：[app/main.py:245-258](file:///d:/A_zidonghuapingtai/app/main.py#L245-L258)（仅 CORS + GZip 中间件，无安全头中间件）
* **影响**：缺 `X-Content-Type-Options: nosniff`、`X-Frame-Options`/`frame-ancestors`、`Referrer-Policy`、`Permissions-Policy`，配合 SEC-08 上传可执行内容可被浏览器误识别 MIME 而执行。
* **修复**：添加 `SecurityHeadersMiddleware` 或在反向代理层统一注入。

---

## Low

### SEC-10：第三方 CDN 资源无 SRI

* **规则 ID**：JS-SRI-001
* **严重度**：Low
* **位置**：[static/index.html:9](file:///d:/A_zidonghuapingtai/static/index.html#L9), [static/admin/templates.html:9](file:///d:/A_zidonghuapingtai/static/admin/templates.html#L9), [static/admin/heal-logs.html:9](file:///d:/A_zidonghuapingtai/static/admin/heal-logs.html#L9)
* **证据**：`<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC..." />` 无 `integrity` 属性。
* **影响**：CDN 被入侵或被劫持时可注入恶意 CSS/JS。
* **修复**：添加 `integrity="sha384-..."` + `crossorigin="anonymous"`；或自托管字体。

### SEC-11：备份文件 `app.js.bak` 公开可访问

* **规则 ID**：信息泄露
* **严重度**：Low
* **位置**：[static/app.js.bak](file:///d:/A_zidonghuapingtai/static/app.js.bak)
* **影响**：`StaticFiles` 挂载在 `/static`，备份文件可被匿名访问 `https://host/static/app.js.bak`，泄露前端源码与 API 调用结构。
* **修复**：删除 `.bak` 文件；`.gitignore` 已应忽略 `*.bak`，确认未被提交到 git 历史。

---

## 其他观察（非问题，供参考）

* **JWT 仅校验 `sub` + `exp`**（[app/security.py:97](file:///d:/A_zidonghuapingtai/app/security.py#L97)）：单服务部署可接受；若后续扩展多服务需补 `iss`/`aud`。
* **SSRF 防护较完善**：`validate_proxy_target` 已校验 scheme 白名单、拒绝本机/内网 IP、跨域重定向剥离 Authorization（[app/core/utils.py:3338-3394](file:///d:/A_zidonghuapingtai/app/core/utils.py#L3338)），实现质量较高。
* **SQL 注入防护到位**：未发现字符串拼接 SQL，dashboard 用 `text()` + 参数绑定 `:pid`（[app/main.py:355-364](file:///d:/A_zidonghuapingtai/app/main.py#L355)）。
* **密码存储正确**：bcrypt via passlib（[app/security.py:58, 73](file:///d:/A_zidonghuapingtai/app/security.py#L58)），未发现明文/MD5/SHA256 回退。
* **登录有限流**：`_check_login_rate_limit` 存在（[app/main.py:324](file:///d:/A_zidonghuapingtai/app/main.py#L324)）。
* **子进程调用安全**：`subprocess.run([python_path, str(PADDLE_OCR_WORKER)], ...)` 用列表形式无 `shell=True`（[app/functional_testing.py:738](file:///d:/A_zidonghuapingtai/app/functional_testing.py#L738)）；curl.exe 也是列表参数（[app/vendor/piliangtianjiagouwuche.py:432](file:///d:/A_zidonghuapingtai/app/vendor/piliangtianjiagouwuche.py#L432)）。

---

## 修复优先级建议

| 优先级 | 编号 | 描述 | 工作量 |
|--------|------|------|--------|
| P0 | SEC-01 | 任意文件读取漏洞 | 小 |
| P0 | SEC-04 | localStorage 存 token + 明文密码 | 中 |
| P1 | SEC-05 + SEC-08 | 上传无大小/内容校验 | 小 |
| P1 | SEC-06 | innerHTML 存储型 XSS | 中（需逐处排查） |
| P1 | SEC-03 | OpenAPI 文档关闭 | 极小 |
| P2 | SEC-02 | CORS 收紧 | 极小 |
| P2 | SEC-07 + SEC-09 | CSP + 安全响应头 | 小 |
| P3 | SEC-10, SEC-11 | SRI + 删除 bak | 极小 |

---

## 下一步

请阅读本报告后告知是否开始修复。建议从 **SEC-01** 开始逐项处理，每项修复后跑一次相关测试（`tests/` 下已有测试用例）确认无回归。
