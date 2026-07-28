/**
 * auth API 模块
 * 对应后端 app/routers/auth.py（2 个端点）
 */
import { api } from '../client.js'

// POST /api/auth/login — 登录
export function login(username, password) {
  return api('/api/auth/login', {
    method: 'POST',
    body: { username, password },
  })
}

// GET /api/auth/me — 当前用户信息
export function getMe() {
  return api('/api/auth/me')
}
