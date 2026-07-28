/**
 * Test Accounts API 模块
 * 对齐旧应用 /api/test-accounts + /api/test-account-bindings 接口调用
 *
 * 后端：app/routers/test_accounts.py
 *   - GET    /api/test-accounts              列表（支持 project_id 过滤）
 *   - POST   /api/test-accounts              创建（require_admin）
 *   - PUT    /api/test-accounts/{id}         更新（require_admin）
 *   - DELETE /api/test-accounts/{id}         删除（require_admin）
 *
 *   - PUT    /api/test-account-bindings      绑定/解绑（require_admin）
 *     body: { target_type, target_id, account_profile_id }
 */
import { api } from '../client.js'

export function listTestAccounts(projectId) {
  const qs = projectId ? `?project_id=${projectId}` : ''
  return api(`/api/test-accounts${qs}`)
}

export function createTestAccount(data) {
  return api('/api/test-accounts', { method: 'POST', body: data })
}

export function updateTestAccount(id, data) {
  return api(`/api/test-accounts/${id}`, { method: 'PUT', body: data })
}

export function deleteTestAccount(id) {
  return api(`/api/test-accounts/${id}`, { method: 'DELETE' })
}

/** 绑定/解绑测试账号到目标（project/functional_task/functional_case/ui_case） */
export function saveTestAccountBinding(targetType, targetId, accountProfileId) {
  return api('/api/test-account-bindings', {
    method: 'PUT',
    body: {
      target_type: targetType,
      target_id: Number(targetId),
      account_profile_id: accountProfileId ? Number(accountProfileId) : null,
    },
  })
}
