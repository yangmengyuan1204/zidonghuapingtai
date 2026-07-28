/**
 * Api Cases API 模块
 * 对齐旧应用 /api/api-cases 接口调用
 *
 * 后端：app/routers/api_cases.py
 *   - GET    /api/api-cases                       列表（支持 project_id / env_id / page / page_size）
 *   - POST   /api/api-cases                       新增
 *   - PUT    /api/api-cases/{id}                  更新
 *   - DELETE /api/api-cases/{id}                  删除
 *   - POST   /api/api-cases/{id}/execute          单条执行
 *   - POST   /api/api-cases/batch-execute         批量执行
 */
import { api } from '../client.js'

export function listApiCases(params = {}) {
  const qs = new URLSearchParams()
  if (params.projectId) qs.set('project_id', params.projectId)
  if (params.envId) qs.set('env_id', params.envId)
  if (params.page) qs.set('page', params.page)
  if (params.pageSize) qs.set('page_size', params.pageSize)
  const query = qs.toString()
  return api(`/api/api-cases${query ? `?${query}` : ''}`)
}

export function createApiCase(data) {
  return api('/api/api-cases', { method: 'POST', body: data })
}

export function updateApiCase(id, data) {
  return api(`/api/api-cases/${id}`, { method: 'PUT', body: data })
}

export function deleteApiCase(id) {
  return api(`/api/api-cases/${id}`, { method: 'DELETE' })
}

export function executeApiCase(id, body = {}) {
  return api(`/api/api-cases/${id}/execute`, { method: 'POST', body })
}

export function batchExecuteApiCases(payload) {
  return api('/api/api-cases/batch-execute', { method: 'POST', body: payload })
}
