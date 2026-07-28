<template>
  <div class="shell">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="brand">
        <strong>AI 功能测试工作台</strong>
        <span>{{ auth.user?.username || '' }}</span>
      </div>
      <nav class="nav" id="mainNav">
        <button
          v-for="item in visibleViews"
          :key="item.key"
          :class="{ active: isActive(item.key) }"
          @click="navigate(item)"
        >
          {{ item.label }}
        </button>
      </nav>
      <div class="sidebar-foot">
        <span class="role-pill">{{ auth.user?.role || '' }}</span>
        <a
          v-if="auth.isAdmin"
          href="/static/admin/templates.html"
          target="_blank"
          style="display:block;font-size:12px;margin-top:6px;color:var(--accent)"
        >模板管理</a>
        <a
          v-if="auth.isAdmin"
          href="/static/admin/heal-logs.html"
          target="_blank"
          style="display:block;font-size:12px;color:var(--accent)"
        >自愈记录</a>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main">
      <header class="topbar">
        <h2 id="viewTitle">{{ currentLabel }}</h2>
        <div class="topbar-actions">
          <!-- 全局 AI 配置按钮（仅 admin） -->
          <button
            v-if="auth.isAdmin"
            class="btn secondary"
            type="button"
            @click="showAiConfigPlaceholder"
          >全局 AI 配置</button>

          <!-- 主题切换 -->
          <div class="theme-picker">
            <button
              v-for="t in themeOptions"
              :key="t.value"
              class="theme-dot"
              :class="{ active: themeStore.theme === t.value }"
              :style="{ background: t.color }"
              :title="t.title"
              @click="themeStore.applyTheme(t.value)"
            />
          </div>

          <!-- 退出 -->
          <button class="btn secondary" type="button" @click="handleLogout">退出</button>
        </div>
      </header>
      <section class="content" id="content">
        <router-view />
      </section>
    </main>
  </div>
</template>

<script setup>
/**
 * 主布局壳
 * 对齐旧应用 app.js renderShell 的结构：
 * div.shell > aside.sidebar + main.main > header.topbar + section.content
 */
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useThemeStore } from '../stores/theme.js'
import { useToastStore } from '../stores/toast.js'
import { menuViews } from '../router/index.js'
import { navigateToView, navigateAfterLogout } from '../services/navigation.js'

const auth = useAuthStore()
const themeStore = useThemeStore()
const toast = useToastStore()
const route = useRoute()

const themeOptions = [
  { value: 'shuimo', color: '#2f4f46', title: '水墨' },
  { value: 'zhuanye', color: '#6366f1', title: '专业蓝灰' },
  { value: 'qingxuan', color: '#3b82f6', title: '清爽浅色' },
  { value: 'xiaolan', color: '#ff6b9d', title: '小兰' },
]

// 过滤 adminOnly 菜单
const visibleViews = computed(() =>
  menuViews.filter((item) => !item.adminOnly || auth.isAdmin)
)

const currentLabel = computed(() => {
  const view = menuViews.find((v) => v.key === route.meta.viewKey)
  return view?.label || 'AI 功能测试工作台'
})

function isActive(key) {
  return route.meta.viewKey === key
}

function navigate(item) {
  // 统一交由导航服务决策（已迁移→Vue Router，未迁移→旧应用）
  navigateToView(item.key)
}

function handleLogout() {
  auth.logout()
  navigateAfterLogout()
}

function showAiConfigPlaceholder() {
  toast.show('AI 配置功能将在后续 Phase 迁移')
}

onMounted(async () => {
  // 确保用户信息已加载
  if (auth.isLoggedIn && !auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      // fetchMe 失败时由 401 拦截器处理
    }
  }
})
</script>

<style scoped>
/* 使用旧应用 .shell / .sidebar / .nav / .topbar / .content 样式（来自 legacy.css） */
</style>
