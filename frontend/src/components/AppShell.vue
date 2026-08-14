<template>
  <div class="v2-shell" @keydown.esc="closeDrawer">
    <button
      v-if="drawerOpen"
      class="v2-shell__backdrop"
      type="button"
      aria-label="关闭主导航"
      @click="closeDrawer"
    />

    <aside
      id="v2-shell-sidebar"
      class="v2-shell__sidebar"
      :class="{ 'v2-shell__sidebar--open': drawerOpen }"
    >
      <div class="v2-shell__brand">
        <span class="v2-shell__brand-mark" aria-hidden="true">Q</span>
        <div class="v2-shell__brand-copy">
          <strong>质量工作台</strong>
          <span>AI TEST OPERATIONS</span>
        </div>
        <button class="v2-shell__drawer-close" type="button" aria-label="关闭主导航" @click="closeDrawer">×</button>
      </div>

      <div class="v2-shell__project-context">
        <span class="v2-shell__context-label">当前项目</span>
        <div class="v2-shell__project-card">
          <span class="v2-shell__project-dot" aria-hidden="true" />
          <BaseSelect
            class="v2-shell__project-select"
            :model-value="app.filters.projectId"
            :options="projectOptions"
            aria-label="切换当前项目"
            @update:model-value="handleProjectChange"
          />
        </div>
      </div>

      <nav id="mainNav" class="v2-shell__nav" aria-label="主导航">
        <section v-for="group in groupedViews" :key="group.label" class="v2-shell__nav-group">
          <h2 class="v2-shell__nav-heading">{{ group.label }}</h2>
          <BaseButton
            v-for="item in group.items"
            :key="item.key"
            class="v2-shell__nav-button"
            :class="{ 'v2-shell__nav-button--active': isActive(item.key) }"
            variant="ghost"
            block
            :aria-current="isActive(item.key) ? 'page' : undefined"
            @click="navigate(item)"
          >
            <span class="v2-shell__nav-label">{{ item.label }}</span>
          </BaseButton>
        </section>
      </nav>

      <div class="v2-shell__sidebar-foot">
        <div class="v2-shell__account">
          <span class="v2-shell__avatar" aria-hidden="true">{{ userInitial }}</span>
          <span class="v2-shell__account-copy">
            <strong>{{ auth.user?.username || '当前用户' }}</strong>
            <small>{{ auth.user?.role || '' }}</small>
          </span>
          <BaseBadge class="v2-shell__role" tone="neutral">{{ auth.isAdmin ? '管理员' : '成员' }}</BaseBadge>
        </div>
        <div v-if="auth.isAdmin" class="v2-shell__admin-links">
          <a class="v2-shell__admin-link" :href="adminPageHref('templates.html')">模板管理</a>
          <a class="v2-shell__admin-link" :href="adminPageHref('heal-logs.html')">自愈记录</a>
        </div>
      </div>
    </aside>

    <main class="v2-shell__main">
      <header class="v2-shell__topbar">
        <div class="v2-shell__topbar-leading">
          <button
            class="v2-shell__drawer-trigger"
            type="button"
            aria-label="打开主导航"
            aria-controls="v2-shell-sidebar"
            :aria-expanded="drawerOpen"
            @click="drawerOpen = true"
          >
            <span aria-hidden="true">☰</span>
          </button>
          <div class="v2-shell__breadcrumb">
            <span>{{ currentGroupLabel }}</span>
            <span aria-hidden="true">/</span>
            <h1 id="viewTitle">{{ currentLabel }}</h1>
          </div>
        </div>

        <div class="v2-shell__topbar-actions">
          <BaseButton
            v-if="auth.isAdmin"
            class="v2-shell__topbar-action"
            variant="secondary"
            type="button"
            @click="aiConfigOpen = true"
          >全局 AI 配置</BaseButton>
          <BaseButton class="v2-shell__topbar-action" variant="secondary" type="button" @click="handleLogout">退出</BaseButton>
        </div>
      </header>
      <section id="content" class="v2-shell__content">
        <router-view :key="route.name || route.path" />
      </section>
    </main>
    <AiConfigDialog v-if="auth.isAdmin" v-model:open="aiConfigOpen" />
  </div>
</template>

<script setup>
/**
 * 主布局壳
 * 对齐旧应用 app.js renderShell 的结构：
 * div.shell > aside.sidebar + main.main > header.topbar + section.content
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BaseBadge, BaseButton, BaseSelect } from './v2/base/index.js'
import AiConfigDialog from './AiConfigDialog.vue'
import { useAppStore } from '../stores/app.js'
import { useAuthStore } from '../stores/auth.js'
import { useThemeStore } from '../stores/theme.js'
import { menuViews } from '../router/index.js'
import { navigateToView, navigateAfterLogout } from '../services/navigation.js'

const auth = useAuthStore()
const app = useAppStore()
useThemeStore() // 初始化 Forest Light 主题锁定
const route = useRoute()
const router = useRouter()
const drawerOpen = ref(false)
const aiConfigOpen = ref(false)
const projects = ref([])

const navigationGroups = [
  { label: '工作空间', keys: ['dashboard', 'projects'] },
  { label: '测试资产', keys: ['apiCases'] },
  { label: '自动化执行', keys: ['dataScripts', 'requirementVerification', 'uiCases', 'systemRegression', 'records'] },
  { label: '系统管理', keys: ['users'] },
]
const iconPaths = {
  dashboard: 'M4 4h6v6H4V4Zm10 0h6v10h-6V4ZM4 14h6v6H4v-6Zm10 4h6v2h-6v-2Z',
  projects: 'M3 7h7l2 2h9v10H3V7Z',
  apiCases: 'M5 4h14v16H5V4Zm3 4h8M8 12h8M8 16h5',
  dataScripts: 'M8 4 3 12l5 8M16 4l5 8-5 8M14 3l-4 18',
  requirementVerification: 'M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6l-7-3Zm-3 9 2 2 4-5',
  uiCases: 'M3 5h18v12H3V5Zm5 16h8M12 17v4',
  records: 'M5 4h14v16H5V4Zm3 4h8M8 12h8M8 16h4',
  systemRegression: 'M4 7h16v11H4V7Zm4-3h8v3H8V4Zm0 8 2 2 5-5m-8 9h10',
  users: 'M8 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm8-1a3 3 0 1 0 0-6M2 21c0-4 2-7 6-7s6 3 6 7m1-7c4 0 7 2 7 6',
}

const visibleViews = computed(() => menuViews.filter((item) => !item.adminOnly || auth.isAdmin))
const groupedViews = computed(() => navigationGroups
  .map((group) => ({ ...group, items: group.keys.map((key) => visibleViews.value.find((item) => item.key === key)).filter(Boolean) }))
  .filter((group) => group.items.length))
const projectOptions = computed(() => [
  { value: '', label: '全部项目' },
  ...projects.value.map((item) => ({ value: String(item.id), label: item.name })),
])
const userInitial = computed(() => String(auth.user?.username || 'U').slice(0, 1).toUpperCase())

const currentLabel = computed(() => {
  const view = menuViews.find((v) => v.key === route.meta.viewKey)
  return view?.label || 'AI 功能测试工作台'
})
const currentGroupLabel = computed(() => navigationGroups.find((group) => group.keys.includes(route.meta.viewKey))?.label || '工作空间')

function isActive(key) {
  return route.meta.viewKey === key
}

function adminPageHref(page) {
  const returnPath = `/v3${route.path || '/dashboard'}`
  const params = new URLSearchParams({
    ui: '20260812-v3-admin-1',
    return: returnPath,
  })
  return `/static/admin/${page}?${params.toString()}`
}

function navigate(item) {
  closeDrawer()
  navigateToView(item.key)
}

function closeDrawer() {
  drawerOpen.value = false
}

watch(
  () => route.fullPath,
  () => {
    closeDrawer()
    aiConfigOpen.value = false
  },
)

function handleProjectChange(projectId) {
  const nextProjectId = String(projectId || '')
  if (nextProjectId === String(app.filters.projectId || '')) return
  app.setProjectId(nextProjectId)
  closeDrawer()
  router.go(0)
}

function handleLogout() {
  auth.logout()
  navigateAfterLogout()
}

onMounted(async () => {
  try {
    projects.value = await app.fetchProjects()
  } catch {
    projects.value = []
  }
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
.v2-shell {
  --v2-layout-sidebar: var(--v2-shell-pilot-sidebar-width);
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--v2-layout-sidebar) minmax(0, 1fr);
  background: var(--v2-shell-pilot-workspace-surface);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

.v2-shell__sidebar {
  position: sticky;
  top: 0;
  z-index: var(--v2-z-sidebar);
  width: var(--v2-shell-pilot-sidebar-width);
  min-width: var(--v2-shell-pilot-sidebar-width);
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--v2-shell-pilot-sidebar-surface);
  border-right: var(--v2-border-width) solid var(--v2-shell-pilot-sidebar-border);
  color: var(--v2-shell-pilot-sidebar-text);
}

.v2-shell__brand {
  display: flex;
  height: var(--v2-shell-pilot-topbar-height);
  min-height: var(--v2-shell-pilot-topbar-height);
  align-items: center;
  gap: var(--v2-space-2);
  padding: 0 16px;
  border-bottom: var(--v2-border-width) solid var(--v2-shell-pilot-sidebar-border);
}

.v2-shell__brand-mark {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--v2-shell-pilot-primary) 0%, #7c3aed 100%);
  color: #ffffff;
  font-family: inherit;
  font-size: 15px;
  font-weight: 600;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.v2-shell__brand-copy {
  min-width: 0;
}

.v2-shell__brand-copy strong,
.v2-shell__brand-copy span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-shell__brand-copy strong {
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.25;
}

.v2-shell__brand-copy span {
  margin-top: 2px;
  color: var(--v2-shell-pilot-sidebar-muted);
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.v2-shell__project-context {
  display: grid;
  gap: 0;
  padding: 16px;
  border-bottom: var(--v2-border-width) solid var(--v2-shell-pilot-sidebar-border);
}

.v2-shell__context-label,
.v2-shell__nav-heading {
  color: var(--v2-shell-pilot-sidebar-muted);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.v2-shell__context-label {
  margin: 0 0 8px;
}

.v2-shell__project-card {
  --v2-select-height: 36px;
  --v2-select-padding: 8px;
  --v2-select-font-size: 13px;
  --v2-select-surface: var(--v2-color-sidebar-surface);
  --v2-select-text: #e5e7eb;
  --v2-select-border: transparent;
  --v2-select-border-hover: transparent;
  --v2-select-border-focus: transparent;
  --v2-select-focus-ring: none;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  min-height: 36px;
  padding: 0 6px 0 10px;
  border: var(--v2-border-width) solid var(--v2-color-sidebar-field-border);
  border-radius: 7px;
  background: var(--v2-color-sidebar-surface);
  color: #e5e7eb;
  color-scheme: dark;
  transition: border-color var(--v2-motion-duration) var(--v2-motion-easing), box-shadow var(--v2-motion-duration) var(--v2-motion-easing);
}

.v2-shell__project-card:focus-within {
  border-color: var(--v2-color-sidebar-accent);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.18);
}

.v2-shell__project-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--v2-radius-round);
  background: var(--v2-feedback-success);
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.18);
}

.v2-shell__project-select {
  width: 100%;
  min-width: 0;
}

.v2-shell__project-card :deep(.v2-base-select),
.v2-shell__project-card :deep(.v2-base-select__native) {
  width: 100%;
  color: #e5e7eb;
  background: var(--v2-color-sidebar-surface);
  background-color: var(--v2-color-sidebar-surface);
  border-color: transparent;
  box-shadow: none;
  font-weight: 500;
  color-scheme: dark;
}

.v2-shell__project-card :deep(.v2-base-select__native option),
.v2-shell__project-card :deep(.v2-shell__project-select option) {
  background: var(--v2-color-sidebar-surface);
  color: #e5e7eb;
}

.v2-shell__nav {
  position: relative;
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 8px 0 16px;
  scrollbar-width: none;
}

.v2-shell__nav-group + .v2-shell__nav-group {
  margin-top: 4px;
}

.v2-shell__nav-heading {
  margin: 18px 0 8px;
  padding: 0 16px;
}

.v2-shell__nav-button {
  --v2-button-height: var(--v2-shell-pilot-menu-item-height);
  --v2-button-radius: 6px;
  --v2-button-border-width: 0px;
  --v2-button-padding: 12px;
  --v2-button-font-size: 13px;
  --v2-button-font-weight: 500;
  --v2-button-ghost-text: var(--v2-shell-pilot-sidebar-text);
  --v2-button-ghost-text-hover: #ffffff;
  --v2-button-ghost-bg: transparent;
  --v2-button-ghost-bg-hover: var(--v2-shell-pilot-sidebar-item-hover);
  --v2-button-ghost-bg-pressed: var(--v2-shell-pilot-sidebar-item-active);
  position: relative;
  display: flex;
  width: calc(100% - 16px);
  margin: 0 0 4px 8px;
  justify-content: flex-start;
  gap: 0;
  overflow: hidden;
  text-align: left;
}

.v2-shell__nav-button :deep(.v2-base-button__content) {
  width: 100%;
  justify-content: flex-start;
}

.v2-shell__nav-button::before {
  position: absolute;
  top: 50%;
  left: 0;
  width: 2px;
  height: 18px;
  border-radius: 0 2px 2px 0;
  background: var(--v2-shell-pilot-sidebar-indicator);
  content: "";
  transform: translateY(-50%) scaleY(0);
  transition: transform var(--v2-motion-duration) var(--v2-motion-easing);
}

.v2-shell__nav-button--active::before {
  transform: translateY(-50%) scaleY(1);
}

.v2-shell__nav-button--active {
  --v2-button-ghost-bg: var(--v2-shell-pilot-sidebar-item-active);
  --v2-button-ghost-text: #ffffff;
  --v2-button-font-weight: 600;
}

.v2-shell__nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-shell__sidebar-foot {
  padding: 12px 14px;
  border-top: var(--v2-border-width) solid var(--v2-shell-pilot-sidebar-border);
  background: var(--v2-shell-pilot-sidebar-surface);
}

.v2-shell__account {
  display: flex;
  align-items: center;
  gap: 10px;
}

.v2-shell__avatar {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: var(--v2-radius-round);
  background: var(--v2-shell-pilot-sidebar-item-active);
  color: #93c5fd;
  font-size: 13px;
  font-weight: 600;
}

.v2-shell__account-copy {
  display: grid;
  min-width: 0;
  flex: 1;
}

.v2-shell__account-copy strong,
.v2-shell__account-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-shell__account-copy strong {
  color: #ffffff;
  font-size: 13px;
  font-weight: 500;
}

.v2-shell__account-copy small {
  color: var(--v2-shell-pilot-sidebar-muted);
  font-size: 11px;
}

.v2-shell__role {
  --v2-badge-height: 22px;
  --v2-badge-padding: 6px;
  --v2-badge-font-size: 10px;
  --v2-badge-surface: rgba(255, 255, 255, 0.08);
  --v2-badge-text: var(--v2-shell-pilot-sidebar-muted);
}

.v2-shell__admin-links {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 10px;
}

.v2-shell__admin-link {
  padding: 4px 8px;
  border-radius: 6px;
  color: var(--v2-shell-pilot-sidebar-muted);
  font-size: 12px;
  line-height: 1.4;
  text-decoration: none;
  transition:
    color var(--v2-motion-duration) var(--v2-motion-easing),
    background-color var(--v2-motion-duration) var(--v2-motion-easing);
}

.v2-shell__admin-link:hover {
  background: var(--v2-shell-pilot-sidebar-item-hover);
  color: #ffffff;
}

.v2-shell__main {
  position: relative;
  z-index: var(--v2-z-base);
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--v2-shell-pilot-workspace-surface);
}

.v2-shell__topbar {
  position: sticky;
  top: 0;
  z-index: var(--v2-z-sticky);
  height: var(--v2-shell-pilot-topbar-height);
  min-height: var(--v2-shell-pilot-topbar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-3);
  padding: 0 24px;
  background: #ffffff;
  border-bottom: var(--v2-border-width) solid var(--v2-shell-pilot-card-border);
}

.v2-shell__topbar-leading {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--v2-space-1);
}

.v2-shell__breadcrumb {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  color: var(--v2-shell-pilot-text-muted);
  font-size: 13px;
}

.v2-shell__breadcrumb > span {
  color: var(--v2-shell-pilot-text-muted);
}

.v2-shell__breadcrumb h1 {
  margin: 0;
  overflow: hidden;
  color: var(--v2-shell-pilot-text-heading);
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-shell__topbar-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.v2-shell__topbar-action {
  --v2-button-height: 34px;
  --v2-button-radius: 7px;
  --v2-button-padding: 10px;
  --v2-button-font-size: 12px;
  --v2-button-secondary-bg: transparent;
  --v2-button-secondary-border: transparent;
  --v2-button-secondary-text: var(--v2-shell-pilot-text-secondary);
  --v2-button-secondary-bg-hover: var(--v2-color-surface-soft-neutral);
  --v2-button-secondary-bg-pressed: var(--v2-color-surface-soft-neutral);
}

.v2-shell__content {
  padding: 28px 28px 32px;
  flex: 1 1 auto;
  min-height: 0;
}

.v2-shell__content > * {
  width: 100%;
  max-width: var(--v2-shell-pilot-content-max);
  margin-inline: auto;
}

.v2-shell__content:has(.v2-legacy-embed) {
  display: flex;
  flex-direction: column;
  padding: 0;
}

.v2-shell__content:has(.v2-legacy-embed) > * {
  max-width: none;
  margin-inline: 0;
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
}

.v2-shell__drawer-trigger,
.v2-shell__drawer-close,
.v2-shell__backdrop {
  display: none;
}

.v2-shell__drawer-trigger:focus-visible,
.v2-shell__drawer-close:focus-visible {
  outline: 0;
  box-shadow: var(--v2-state-focus-ring);
}

@media (min-width: 1081px) and (max-width: 1599px) {
  .v2-shell__content {
    padding: 24px 24px 32px;
  }

  .v2-shell__content:has(.v2-legacy-embed) {
    padding: 0;
  }
}

@media (max-width: 1080px) {
  .v2-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .v2-shell__sidebar {
    position: fixed;
    top: 0;
    left: 0;
    z-index: calc(var(--v2-z-sidebar) + 1);
    width: min(300px, 86vw);
    min-width: min(300px, 86vw);
    transform: translateX(-100%);
    transition: transform var(--v2-motion-duration-dialog) var(--v2-motion-easing-standard);
    box-shadow: var(--v2-shadow-dropdown);
  }

  .v2-shell__sidebar--open {
    transform: translateX(0);
  }

  .v2-shell__backdrop {
    position: fixed;
    inset: 0;
    z-index: var(--v2-z-sidebar);
    display: block;
    width: 100%;
    height: 100%;
    padding: 0;
    border: 0;
    background: var(--v2-surface-overlay);
  }

  .v2-shell__drawer-trigger {
    display: inline-grid;
    width: 34px;
    height: 34px;
    flex: 0 0 auto;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: var(--v2-radius-sm);
    background: transparent;
    color: var(--v2-shell-pilot-text-secondary);
    cursor: pointer;
    font-size: 16px;
  }

  .v2-shell__drawer-trigger:hover {
    background: var(--v2-color-surface-soft-neutral);
    color: var(--v2-shell-pilot-text-heading);
  }

  .v2-shell__drawer-close {
    display: inline-grid;
    width: 28px;
    height: 28px;
    flex: 0 0 auto;
    margin-left: auto;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: var(--v2-radius-sm);
    background: transparent;
    color: var(--v2-shell-pilot-sidebar-muted);
    cursor: pointer;
    font-size: 18px;
  }

  .v2-shell__drawer-close:hover {
    background: var(--v2-shell-pilot-sidebar-item-hover);
    color: #ffffff;
  }
}

@media (max-width: 720px) {
  .v2-shell__topbar {
    padding: 0 12px;
  }

  .v2-shell__content {
    padding: 16px 16px 28px;
  }

  .v2-shell__content:has(.v2-legacy-embed) {
    padding: 0;
  }

  .v2-shell__breadcrumb > span {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .v2-shell__sidebar {
    transition-duration: var(--v2-motion-reduced);
  }
}
</style>
