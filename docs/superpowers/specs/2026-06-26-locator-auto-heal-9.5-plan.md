# Locator 自动自愈 9.5 分实施计划

## 当前状态：7.5 分

已完成：核心 AI 自愈链路（DOM 提取 → AI 推断 → 验证 → 写回 → 审计日志），密码脱敏，JS 注入防护，全 action 覆盖，规则自愈 + AI 自愈双路径。

## 目标：9.5 分

补齐 5 个维度缺口，使自愈功能达到生产可用水准。

---

## 阶段一：8.5 分（核心补齐）

### 1. 批量执行支持 [B4]

**问题：** `execute_ui_cases_batch` 不传 db_session，批量执行时 AI 自愈不生效。

**方案：**

```
execute_ui_cases_batch 签名新增 db_session 参数
    ↓
单线程分支：传给 execute_ui_case_with_deadline → execute_ui_case
多线程分支：每个 worker 从 SessionLocal() 新建独立 session
降级分支：传 None，跳过 AI 自愈
```

**改动文件：**
- `app/executors.py` - `execute_ui_cases_batch` / `execute_ui_case_with_deadline` 签名
- `app/routers/functional_tasks.py` - 调用处传入 bg_db

**多线程 session 策略：**
```python
def _worker(case, variables, execution_context, db_session_factory):
    session = db_session_factory()  # 每个线程独立 session
    try:
        return execute_ui_case(case, variables, execution_context, db_session=session)
    finally:
        session.close()
```

### 2. confidence 阈值过滤

**问题：** AI 返回 confidence=0.3 的低质量建议也会自动应用。

**方案：**
- `AiConfig` 新增字段 `heal_confidence_threshold`（默认 0.7）
- `auto_heal` 中 AI 返回 confidence < 阈值时，记录日志但 `auto_applied=0`
- 用户可在 heal-logs 页面手动确认

**改动文件：**
- `app/models.py` - `AiConfig` 加字段
- `app/core/utils.py` - 迁移配置
- `app/services/locator_heal.py` - `auto_heal` 增加阈值判断
- `app/main.py` - AI 配置接口暴露字段

### 3. AI 重试机制

**问题：** AI 调用失败或返回无效结果时直接放弃，无重试。

**方案：**
- 第 1 次：标准 prompt
- 第 2 次（仅当第 1 次失败）：精简 prompt（只传 failed_locator + 元素 tag/text，去掉 candidates）
- 最多重试 1 次，避免拖慢执行

**改动文件：**
- `app/services/locator_heal.py` - `auto_heal` 内部增加重试循环

---

## 阶段二：9 分（可观测性）

### 4. 前端 heal 日志页

**问题：** heal 记录只能通过 API 查看，用户无法在界面上审阅 AI 推理过程。

**方案：**

新增页面 `/ui-cases/heal-logs.html`：

```
┌─────────────────────────────────────────────────┐
│  Locator 自愈日志                                │
├──────────┬──────────┬──────────┬────────────────┤
│ 用例名    │ 失效定位  │ 新定位    │ 状态           │
│          │          │          │ ✅已自动应用    │
│          │          │          │ ⚠️待确认       │
│          │          │          │ ❌验证失败      │
├──────────┴──────────┴──────────┴────────────────┤
│ [展开详情]                                       │
│  步骤动作: click                                 │
│  AI 置信度: 0.92                                 │
│  AI 推理: 按钮文案"登录"未变，id 从 submit 改为  │
│  login-btn                                       │
│  [查看截图] [查看 Prompt] [确认应用] [拒绝]      │
└─────────────────────────────────────────────────┘
```

**功能：**
- 列表展示 heal 记录（分页、按 case_id 筛选）
- 展开/折叠详情（AI prompt、AI response、截图）
- 待确认记录：`确认应用` / `拒绝` 按钮
- 已应用记录：只读

**改动文件：**
- `app/main.py` - 新增 `GET /api/locator-heal-logs` 分页 + `POST /api/locator-heal-logs/{id}/apply`
- `static/heal-logs.html` - 新增页面
- `static/app.js` - heal 日志交互逻辑

### 5. 执行日志增强

**问题：** 执行日志中只显示 `healed: true`，看不到 AI 推理过程。

**方案：**
- step detail 中新增 `heal_info` 字段：
  ```json
  {
    "healed": true,
    "ai_healed": true,
    "healed_locator": "#login-btn",
    "heal_confidence": 0.92,
    "heal_reason": "按钮文案未变，id 改为 login-btn"
  }
  ```
- Allure 报告中展示自愈信息

**改动文件：**
- `app/executors.py` - `_run_ui_step` detail 补充字段
- `app/services/locator_heal.py` - `auto_heal` 返回值改为 dict（locator + confidence + reason）

---

## 阶段三：9.5 分（鲁棒性）

### 6. 元素定位历史学习

**问题：** 同一 locator 反复失效，每次都调 AI 浪费时间。

**方案：**

新增表 `locator_heal_history`：
```sql
CREATE TABLE locator_heal_history (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    old_locator VARCHAR(500),
    new_locator VARCHAR(500),
    apply_count INTEGER DEFAULT 1,   -- 被应用次数
    success_count INTEGER DEFAULT 0, -- 应用后执行成功次数
    last_used DATETIME,
    UNIQUE(project_id, old_locator)
);
```

**工作流：**
```
locator 失效
    ↓
先查 locator_heal_history（项目内是否有相同 old_locator 的历史映射）
    ↓ 命中且 success_count > 0
直接用历史 new_locator（跳过 AI，<10ms）
    ↓ 未命中
调 AI 自愈
    ↓ 成功
写入 / 更新 locator_heal_history
    ↓
用例执行结束后，根据结果更新 success_count
```

**改动文件：**
- `app/models.py` - 新增 `LocatorHealHistory` 模型
- `app/services/locator_heal.py` - `auto_heal` 前先查历史
- `app/executors.py` - 用例执行结束后回调更新 success_count

### 7. Shadow DOM 穿透

**问题：** Web Component（如 lit-element、stencil）的元素在 shadow root 内，`querySelectorAll` 查不到。

**方案：**

递归遍历 shadow root：
```javascript
function deepQueryAll(root, selector) {
    let results = Array.from(root.querySelectorAll(selector));
    for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) {
            results = results.concat(deepQueryAll(el.shadowRoot, selector));
        }
    }
    return results;
}
```

**改动文件：**
- `app/services/locator_heal.py` - `_EXTRACT_JS` 改为深度遍历

### 8. 动态加载元素处理

**问题：** SPA 页面元素延迟渲染，AI 扫描时元素还没出现。

**方案：**
- DOM 提取前增加 `_wait_page_stable(page, timeout=2000)`
- 元素列表为空时，等待 1s 后重试 1 次
- 超时则跳过自愈

**改动文件：**
- `app/services/locator_heal.py` - `auto_heal` 入口增加等待

### 9. 多语言页面支持

**问题：** JS 提取依赖 `button`/`a` 等英文标签，中文页面的自定义组件（如 `<el-button>`）无法识别。

**方案：**
- selector 列表扩展：`button, a, input, textarea, select, [role="button"], [onclick], [class*="btn"], [class*="button"]`
- AI prompt 增加页面 `<html lang>` 信息

**改动文件：**
- `app/services/locator_heal.py` - `_EXTRACT_JS` selector 扩展

---

## 改动文件总览

| 文件 | 阶段一 | 阶段二 | 阶段三 |
|------|--------|--------|--------|
| `app/models.py` | AiConfig 加字段 | - | 新增 LocatorHealHistory |
| `app/core/utils.py` | 迁移配置 | - | - |
| `app/services/locator_heal.py` | 阈值+重试 | 返回值改 dict | 历史学习+Shadow DOM+动态等待 |
| `app/executors.py` | batch 传 db+签名 | detail 增强 | 执行后回调更新历史 |
| `app/main.py` | AI 配置接口 | heal-logs 分页+apply API | - |
| `app/routers/functional_tasks.py` | 传 bg_db | - | - |
| `static/heal-logs.html` | - | 新增 | - |
| `static/app.js` | - | heal 日志交互 | - |

---

## 风险点

| 风险 | 影响 | 缓解 |
|------|------|------|
| 多线程 session 泄漏 | 连接耗尽 | worker 内 try/finally 确保 close |
| 历史学习误判 | 错误映射被反复应用 | success_count 低于阈值时降级回 AI |
| Shadow DOM 递归性能 | 大页面卡顿 | 限制递归深度 ≤ 3 层 |
| AI 重试拖慢执行 | 单步骤耗时翻倍 | 仅重试 1 次，精简 prompt |
| confidence 阈值过高 | AI 建议都被拒绝 | 默认 0.7，可在配置中调整 |

---

## 验收标准

- [ ] 单个 UI 用例执行中 locator 失效，AI 自愈成功率 > 80%
- [ ] 批量执行 10 个用例，AI 自愈正常触发
- [ ] confidence < 0.7 的建议不自动应用，在 heal-logs 页面可手动确认
- [ ] 同一 locator 二次失效，历史学习命中，响应 < 50ms
- [ ] Shadow DOM 页面元素可被提取
- [ ] heal-logs 页面可查看 AI 推理过程和截图
- [ ] AI 未配置/调用失败时，自动降级到规则自愈，不影响执行
