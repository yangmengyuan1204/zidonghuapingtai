/**
 * 测试账号工具函数
 * 对齐旧应用 app.js accountLabel / accountMaskedText
 */

/**
 * 账号档案显示标签：profile_name（范围）
 * 对齐旧应用 accountLabel(account, projects)
 */
export function accountLabel(account, projects = []) {
  if (!account) return ''
  const project = account.project_id
    ? projects.find((item) => String(item.id) === String(account.project_id))
    : null
  const scope = account.project_id
    ? project?.name || `项目#${account.project_id}`
    : '全局'
  return `${account.profile_name}（${scope}）`
}

/**
 * 账号脱敏变量文本（用于 pre.mini-log 展示）
 * 对齐旧应用 accountMaskedText(account)
 */
export function accountMaskedText(account) {
  const values = account?.masked_variables || {}
  const labels = {
    username: '登录账号',
    account: '登录账号',
    password: '登录密码',
    code: '验证码',
    captcha: '验证码',
    captcha_code: '验证码',
    verify_code: '验证码',
    verification_code: '验证码',
  }
  const text = Object.entries(values)
    .map(([key, value]) => `${labels[key] || key}: ${value === '***' ? '已配置' : value}`)
    .join('\n')
  return text || '-'
}
