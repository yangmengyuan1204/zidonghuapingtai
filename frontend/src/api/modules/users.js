/**
 * Users API 模块
 * 对齐旧应用 /api/users 接口调用
 *
 * 后端：app/routers/users.py
 *   - GET    /api/users         列表（require_admin）
 *   - POST   /api/users         创建（require_admin）
 *   - PUT    /api/users/{id}    更新（require_admin）
 *   - DELETE /api/users/{id}    删除（require_admin）
 *
 * 旧应用对应函数：
 *   - renderUsers() → GET /api/users
 *   - userForm(item) → POST/PUT /api/users[/{id}]
 *   - deleteItem(/api/users/{id}, renderUsers) → DELETE
 */
import { api } from '../client.js'

/** 获取用户列表 */
export function listUsers() {
  return api('/api/users')
}

/** 创建用户 */
export function createUser(data) {
  return api('/api/users', { method: 'POST', body: data })
}

/** 更新用户 */
export function updateUser(id, data) {
  return api(`/api/users/${id}`, { method: 'PUT', body: data })
}

/** 删除用户 */
export function deleteUser(id) {
  return api(`/api/users/${id}`, { method: 'DELETE' })
}
