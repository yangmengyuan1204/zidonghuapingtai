/**
 * Auth store — 登录态管理
 * 对齐旧应用 state.token / state.user / isAdmin()
 * 共享 localStorage 'token' key，与旧应用同源
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '../api/modules/auth.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username, password) {
    const result = await authApi.login(username, password)
    token.value = result.access_token
    user.value = result.user
    localStorage.setItem('token', result.access_token)
    return result
  }

  async function fetchMe() {
    if (!token.value) return null
    const me = await authApi.getMe()
    user.value = me
    return me
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  return { token, user, isLoggedIn, isAdmin, login, fetchMe, logout }
})
