/**
 * Envs API 模块
 * 对齐旧应用 /api/envs 接口调用
 *
 * 后端：app/routers/envs.py
 *   - GET    /api/envs              列表（支持 project_id 过滤）
 *   - POST   /api/envs              创建（require_admin）
 *   - PUT    /api/envs/{id}         更新（require_admin）
 *   - DELETE /api/envs/{id}         删除（require_admin）
 */
import { api } from '../client.js'

export function listEnvs(projectId) {
  const qs = projectId ? `?project_id=${projectId}` : ''
  return api(`/api/envs${qs}`)
}

export function createEnv(data) {
  return api('/api/envs', { method: 'POST', body: data })
}

export function updateEnv(id, data) {
  return api(`/api/envs/${id}`, { method: 'PUT', body: data })
}

export function deleteEnv(id) {
  return api(`/api/envs/${id}`, { method: 'DELETE' })
}
