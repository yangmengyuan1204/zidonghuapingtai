<template>
  <section class="login-wrap login-v2">
    <form class="login-panel login-v2-panel" id="loginForm" @submit.prevent="handleLogin">
      <div class="login-v2-brand">
        <span class="login-v2-mark" aria-hidden="true"></span>
        <h1 class="login-v2-title">AI 功能测试工作台</h1>
      </div>
      <p class="login-v2-subtitle">请输入管理员账号登录</p>
      <div class="form-grid login-v2-form">
        <div class="field">
          <label for="username">账号</label>
          <input
            id="username"
            name="username"
            autocomplete="username"
            v-model="username"
            required
          />
        </div>
        <div class="field">
          <label for="password">密码</label>
          <input
            id="password"
            name="password"
            type="password"
            autocomplete="current-password"
            v-model="password"
            required
          />
        </div>
        <label class="check-field remember-check">
          <input id="rememberPwd" name="rememberPwd" type="checkbox" v-model="remember" />
          <span>记住密码</span>
        </label>
        <button
          class="btn login-v2-submit"
          type="submit"
          :class="{ 'is-loading': loading }"
          :disabled="loading"
        >
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </div>
      <div class="login-v2-footer">Enterprise AI Workspace</div>
    </form>
  </section>
</template>

<script setup>
/**
 * 登录页
 * 对齐旧应用 app.js renderLogin：
 * - 读取 savedUsername/savedPassword（base64）
 * - POST /api/auth/login
 * - 登录成功存 token + 记住密码
 *
 * Phase 2：仅视觉 class / 布局节点；不改 id、name、登录逻辑。
 *
 * 注：登录后跳转由 services/navigation.js 统一决策，
 *     LoginView 不直接调用 window.location.href。
 */
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useToastStore } from '../stores/toast.js'
import { navigateAfterLogin } from '../services/navigation.js'

const auth = useAuthStore()
const toast = useToastStore()
const route = useRoute()

const username = ref('')
const password = ref('')
const remember = ref(false)
const loading = ref(false)

onMounted(() => {
  // 读取记住的账号（对齐旧应用 renderLogin 逻辑）
  const savedUsername = localStorage.getItem('savedUsername') || ''
  let savedPassword = ''
  try {
    savedPassword = atob(localStorage.getItem('savedPassword') || '')
  } catch { /* ignore */ }

  username.value = savedUsername
  password.value = savedPassword
  remember.value = !!(savedUsername && savedPassword)
})

async function handleLogin() {
  if (loading.value) return
  loading.value = true
  try {
    await auth.login(username.value, password.value)

    // 记住密码（对齐旧应用 base64 存储，属独立技术债 TD-08）
    if (remember.value) {
      localStorage.setItem('savedUsername', username.value)
      localStorage.setItem('savedPassword', btoa(password.value))
    } else {
      localStorage.removeItem('savedUsername')
      localStorage.removeItem('savedPassword')
    }

    // 登录后跳转交由导航服务统一决策
    const redirect = route.query.redirect
    await navigateAfterLogin(redirect)
  } catch (error) {
    toast.show(error.message)
  } finally {
    loading.value = false
  }
}
</script>
