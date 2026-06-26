# Locator 自动自愈功能设计

## 背景

现有 Locator 自愈只做"手动填 heal_map → 批量回填"，缺少自动发现新 locator 的能力。本次增强目标：UI 用例执行中 locator 失效时，系统自动扫描 DOM、调用 AI 推断新 locator、验证后写回用例并继续执行，无需人工介入。

## 目标

- 执行失败时立即自动修复并继续执行（用户选择 A）
- AI 智能推断 locator 变化（用户选择 B）
- 独立自愈服务 + 执行器回调（方案 B）

## 架构

```
execute_ui_case 执行步骤
    ↓
_resolve_locator 失败（TimeoutError）
    ↓
调用 locator_heal.auto_heal(page, failed_locator, step, db)
    ↓
1. 提取页面 DOM 片段（page.evaluate 抓取可交互元素）
2. 构建 prompt → call_local_model_json（复用现有 AI 配置）
3. AI 返回新 locator JSON
4. page.locator(new).count() 验证唯一性
    ↓
验证通过 → 更新 step + 写 LocatorHealLog + 返回新 locator
验证失败 → 记录失败日志，抛原异常
    ↓
执行器用新 locator 重试该步骤
```

## 新增文件

### `app/services/locator_heal.py`

核心函数：

```python
def auto_heal(page, failed_locator: str, step: dict, db) -> str | None:
    """AI 自动修复失效 locator，返回新 locator 或 None"""
```

流程：
1. `_extract_interactive_elements(page)` - page.evaluate 提取可交互元素
2. `_build_heal_prompt(failed_locator, step, elements)` - 构建 prompt
3. `call_local_model_json(config, prompt)` - 复用现有 AI 调用
4. `_validate_new_locator(page, new_locator, step_action)` - 验证
5. 写 `LocatorHealLog` 记录

## 改动文件

### `app/models.py`

`LocatorHealLog` 新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `step_action` | String(32) | 失效步骤的动作（input/click 等） |
| `ai_prompt` | Text | 存档 prompt 便于调试 |
| `ai_response` | Text | 存档 AI 原始返回 |
| `auto_applied` | Integer | 1=已自动写入用例，0=仅记录 |

### `app/executors.py`

`_resolve_locator` 失败时：
1. 调用 `locator_heal.auto_heal`
2. 成功 → 用新 locator 重试该步骤
3. 失败 → 抛原异常

### `app/main.py`

`heal-steps` 接口保留（手动批量回填仍有用）。

## DOM 提取策略

不传整个 HTML（太大），只提取可交互元素：

```javascript
// page.evaluate 提取
Array.from(document.querySelectorAll('button, a, input, textarea, select, [role="button"], [onclick]')).map(el => ({
  tag: el.tagName.toLowerCase(),
  text: (el.innerText || el.value || '').trim().slice(0, 50),
  id: el.id,
  name: el.name,
  class: el.className,
  placeholder: el.placeholder,
  type: el.type,
  role: el.getAttribute('role'),
  locator_candidates: [
    el.id ? '#' + el.id : '',
    el.name ? `[name="${el.name}"]` : '',
    el.placeholder ? `input[placeholder*="${el.placeholder}"]` : '',
    (el.innerText || el.value) ? `${el.tagName.toLowerCase()}:has-text("${(el.innerText || el.value).trim()}")` : ''
  ].filter(Boolean)
}))
```

## AI Prompt 结构

```
失效的 locator: "button.submit"
步骤动作: click
页面可交互元素列表: [提取的 JSON]

任务：找出最可能对应的新 locator。只返回 JSON：
{"new_locator": "...", "confidence": 0.9, "reason": "按钮文案未变，id 改为 login-btn"}
```

## 验证规则

AI 返回的 locator 必须满足：
- `page.locator(new).count() == 1`（唯一）
- 元素可见（`is_visible()`）
- 与 step.action 兼容（input 需是 input/textarea，click 需是 button/a/[role=button]）

## 失败兜底

- AI 未配置 → 跳过自愈，记录原异常
- AI 返回非法 JSON → 记录原异常
- 验证不通过 → 记录 AI 建议但 `auto_applied=0`，用户可在 heal-logs 里手动确认

## 数据流

| 字段 | 说明 |
|------|------|
| `auto_applied` | 1=已自动写入用例，0=仅记录 |
| `ai_prompt` | 存档 prompt 便于调试 |
| `ai_response` | 存档 AI 原始返回 |

## 影响范围

- 新增 1 个服务文件
- 修改 3 个文件（models/executors/main）
- 不改动数据库表结构（只加字段，SQLite 兼容）
- 不影响现有功能
