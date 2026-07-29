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
          class="sidebar-admin-link"
          href="/static/admin/templates.html"
          target="_blank"
        >模板管理</a>
        <a
          v-if="auth.isAdmin"
          class="sidebar-admin-link"
          href="/static/admin/heal-logs.html"
          target="_blank"
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

          <!-- V2：Forest Light 唯一主题，产品层不再提供多主题切换 -->

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
useThemeStore() // 初始化 Forest Light 主题锁定
const toast = useToastStore()
const route = useRoute()

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
