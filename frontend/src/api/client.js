/**
 * Axios 统一封装
 * 对齐旧应用 app.js#L123 的 api(path, options) 行为：
 * - 自动注入 JWT Authorization header
 * - body 为对象时自动 JSON.stringify + Content-Type
 * - 401 清 token + 跳登录
 * - 统一错误提示（通过 toast store）
 */
import axios from 'axios'
import { useToastStore } from '../stores/toast.js'

const client = axios.create({
  baseURL: '',
  timeout: 30000,
})

// 请求拦截器：注入 JWT
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // body 为对象时自动设置 Content-Type（axios 默认会处理，此处保持与旧应用一致）
  if (config.data && typeof config.data === 'object' && !(config.data instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json'
  }
  return config
})

// 响应拦截器：统一错误处理
client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    let detail = error.message || '请求失败'

    if (status === 401) {
      // 登录失效，清 token + 跳登录
      detail = '登录已失效，请重新登录'
      try {
        const data = error.response.data
        if (data?.detail) detail = data.detail
      } catch { /* ignore */ }
      localStorage.removeItem('token')
      // 跳转登录页（同源，保留当前 path 以便登录后回跳）
      const current = window.location.pathname + window.location.search
      if (!current.startsWith('/v3/login')) {
        window.location.href = '/v3/login?redirect=' + encodeURIComponent(current)
      }
    } else if (error.response) {
      // 提取后端 detail
      try {
        const data = error.response.data
        if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
        else if (typeof data === 'string') detail = data
      } catch { /* ignore */ }
    }

    // 通过 toast store 显示错误
    try {
      const toast = useToastStore()
      toast.show(detail)
    } catch { /* store 未初始化时忽略 */ }

    return Promise.reject(new Error(detail))
  }
)

/**
 * 兼容旧应用 api(path, options) 调用风格
 * @param {string} path - 请求路径，如 /api/auth/login
 * @param {object} options - { method, body, headers, responseType }
 * @returns {Promise<any>}
 */
export async function api(path, options = {}) {
  const config = {
    url: path,
    method: options.method || 'GET',
    headers: options.headers || {},
  }
  if (options.body !== undefined) {
    config.data = options.body
  }
  if (options.responseType) {
    config.responseType = options.responseType
  }
  return client.request(config)
}

export default client
