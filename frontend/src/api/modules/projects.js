/**
 * Projects API 模块
 * 对齐旧应用 /api/projects 接口调用
 *
 * 后端：app/routers/projects.py
 *   - GET    /api/projects          列表（get_current_user）
 *   - POST   /api/projects          创建（require_admin）
 *   - PUT    /api/projects/{id}     更新（require_admin）
 *   - DELETE /api/projects/{id}     删除（require_admin，级联清理）
 */
import { api } from '../client.js'

export function listProjects() {
  return api('/api/projects')
}

export function createProject(data) {
  return api('/api/projects', { method: 'POST', body: data })
}

export function updateProject(id, data) {
  return api(`/api/projects/${id}`, { method: 'PUT', body: data })
}

export function deleteProject(id) {
  return api(`/api/projects/${id}`, { method: 'DELETE' })
}
