/**
 * Badge 工具 — 与旧应用 app.js badge() 完全一致
 *
 * 旧应用 badge(value) 返回 HTML 字符串：
 *   <span class="badge {cls}">{text}</span>
 *
 * 本工具拆分为两个函数，供 Vue 模板使用：
 *   - badgeText(value) → 文本
 *   - badgeClass(value) → CSS 类名（ok/fail/warn/空）
 *
 * 数据来源：static/app.js badge 函数（行 136 附近）
 * 后续 Records 等页面迁移时复用本工具。
 */

const LABELS = {
  passed: '通过',
  failed: '失败',
  active: '启用',
  inactive: '停用',
  admin: '主账号',
  normal: '子账号',
  api: '接口',
  ui: 'UI',
  draft: '草稿',
  uploaded: 'Axure已上传',
  screenshot_uploaded: '截图已上传',
  screenshot_analyzed: '截图已识别',
  requirements_updated: '需求已补充',
  scanned: '页面已扫描',
  cases_generated: '测试点已生成',
  ui_steps_generated: '步骤已生成',
  approved: '已确认',
  queued: '排队中',
  pending: '等待中',
  running: '执行中',
  error: '异常',
  skipped: '已跳过',
  ok: '通过',
  success: '成功',
  done: '完成',
  warning: '预警',
  blocked: '阻塞',
  untested: '未测试',
  unknown: '未知',
  partial: '部分完成',
  auth_blocked: '登录受阻',
  failed_verification: '验证失败',
  axure_bound: '已绑定页面',
  executable: '可执行',
  missing_variables: '缺少变量',
  locator_risk: '定位器风险',
  auth_risk: '登录态风险',
  not_recommended: '不建议自动化',
  needs_review: '需人工确认',
  unchecked: '未检查',
  flaky: '不稳定',
  high: '高',
  medium: '中',
  low: '低',
  critical: '紧急',
  P0: 'P0 紧急',
  P1: 'P1 高',
  P2: 'P2 中',
  P3: 'P3 低',
  '充分': '充分',
  '不足': '不足',
  '缺失': '缺失',
  '需人工确认': '需人工确认',
}

const STATUS_CLASS_MAP = {
  passed: 'ok',
  success: 'ok',
  done: 'ok',
  ok: 'ok',
  active: 'ok',
  approved: 'ok',
  executable: 'ok',
  scanned: 'ok',
  cases_generated: 'ok',
  ui_steps_generated: 'ok',
  screenshot_analyzed: 'ok',
  '充分': 'ok',
  failed: 'fail',
  error: 'fail',
  blocked: 'fail',
  auth_blocked: 'fail',
  failed_verification: 'fail',
  missing_variables: 'fail',
  not_recommended: 'fail',
  flaky: 'fail',
  critical: 'fail',
  P0: 'fail',
  '缺失': 'fail',
  skipped: 'warn',
  pending: 'warn',
  queued: 'warn',
  running: 'warn',
  inactive: 'warn',
  uploaded: 'warn',
  screenshot_uploaded: 'warn',
  requirements_updated: 'warn',
  draft: 'warn',
  needs_review: 'warn',
  unchecked: 'warn',
  untested: 'warn',
  unknown: 'warn',
  partial: 'warn',
  warning: 'warn',
  locator_risk: 'warn',
  auth_risk: 'warn',
  high: 'warn',
  medium: 'warn',
  low: '',
  P1: 'warn',
  P2: 'warn',
  P3: '',
  '不足': 'warn',
  '需人工确认': 'warn',
}

/** 返回 badge 文本（对齐旧应用 labels[value] || value || '-'） */
export function badgeText(value) {
  if (value === undefined || value === null || value === '') return '-'
  return LABELS[value] || String(value)
}

/** 返回 badge CSS 类名（对齐旧应用 statusClassMap[value] || ''） */
export function badgeClass(value) {
  return STATUS_CLASS_MAP[value] || ''
}
