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
            <svg class="v2-shell__nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path :d="iconPaths[item.key] || iconPaths.dashboard" />
            </svg>
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
          <a class="v2-shell__admin-link" href="/static/admin/templates.html" target="_blank">模板管理</a>
          <a class="v2-shell__admin-link" href="/static/admin/heal-logs.html" target="_blank">自愈记录</a>
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
        <router-view />
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
import { computed, onMounted, ref } from 'vue'
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
  { label: '自动化执行', keys: ['dataScripts', 'requirementVerification', 'uiCases', 'records'] },
  { label: '系统管理', keys: ['systemRegression', 'users'] },
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

function navigate(item) {
  // 统一交由导航服务决策（已迁移→Vue Router，未迁移→旧应用）
  navigateToView(item.key)
  closeDrawer()
}

function closeDrawer() {
  drawerOpen.value = false
}

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
    min-height: 100vh;
    display: grid;
    grid-template-columns: var(--v2-shell-sidebar-width) minmax(0, 1fr);
  }

  .v2-shell__sidebar {
    position: relative;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    color: var(--v2-shell-sidebar-text);
    background: var(--v2-shell-sidebar-surface);
    border-right: var(--v2-border-width) solid var(--v2-shell-sidebar-border);
  }

  .v2-shell__brand {
    position: relative;
    z-index: var(--v2-z-base);
    padding: var(--v2-space-5) var(--v2-space-3) var(--v2-space-4);
    border-bottom: var(--v2-border-width) solid var(--v2-shell-sidebar-divider);
  }

  .v2-shell__brand strong {
    display: block;
    color: var(--v2-shell-sidebar-text);
    font-family: var(--v2-font-family-sans);
    font-size: calc(var(--v2-font-size-heading) + var(--v2-space-micro));
    font-weight: var(--v2-font-weight-semibold);
    line-height: 1.25;
    letter-spacing: var(--v2-letter-spacing-wide);
    white-space: nowrap;
  }

  .v2-shell__brand span {
    display: block;
    margin-top: var(--v2-space-1);
    color: var(--v2-shell-sidebar-text-muted);
    font-size: var(--v2-font-size-body);
    font-weight: var(--v2-font-weight-medium);
    line-height: var(--v2-line-height-body);
  }

  .v2-shell__nav {
    position: relative;
    z-index: var(--v2-z-base);
    display: grid;
    gap: var(--v2-space-1);
    padding: var(--v2-space-3) var(--v2-space-2);
  }

  .v2-shell__nav-button {
    --v2-button-height: calc(var(--v2-control-height-default) + var(--v2-space-micro));
    --v2-button-radius: var(--v2-space-2);
    --v2-button-border-width: 0px;
    --v2-button-padding: calc(var(--v2-space-3) + var(--v2-space-micro));
    --v2-button-font-size: calc(var(--v2-font-size-body) + var(--v2-border-width));
    --v2-button-font-weight: var(--v2-font-weight-medium);
    --v2-button-ghost-text: var(--v2-shell-sidebar-text);
    --v2-button-ghost-text-hover: var(--v2-shell-sidebar-text);
    --v2-button-ghost-bg-hover: var(--v2-shell-sidebar-item-hover);
    --v2-button-ghost-bg-pressed: var(--v2-shell-sidebar-item-active);
    justify-content: flex-start;
    overflow: hidden;
    text-align: left;
    letter-spacing: calc(var(--v2-letter-spacing-wide) / 2);
  }

  .v2-shell__nav-button::before {
    position: absolute;
    top: 50%;
    left: 0;
    width: calc(var(--v2-border-width) * 3);
    height: 0;
    background: var(--v2-shell-sidebar-item-indicator);
    border-radius: 0 var(--v2-radius-xs) var(--v2-radius-xs) 0;
    content: "";
    transform: translateY(-50%);
    transition: height var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-shell__nav-button:hover::before,
  .v2-shell__nav-button--active::before {
    height: 72%;
  }

  .v2-shell__nav-button--active {
    --v2-button-ghost-bg: var(--v2-shell-sidebar-item-active);
    --v2-button-font-weight: var(--v2-font-weight-semibold);
  }

  .v2-shell__nav-button :deep(.v2-base-button__content) {
    width: 100%;
    justify-content: flex-start;
  }

  .v2-shell__sidebar-foot {
    position: relative;
    z-index: var(--v2-z-base);
    margin-top: auto;
    padding: var(--v2-space-3) calc(var(--v2-space-2) + var(--v2-space-1) - var(--v2-border-width) * 2);
    border-top: var(--v2-border-width) solid var(--v2-shell-sidebar-divider);
  }

  .v2-shell__role {
    --v2-badge-height: calc(var(--v2-control-height-default) - var(--v2-border-width) * 2);
    --v2-badge-padding: calc(var(--v2-space-3) + var(--v2-space-micro));
    --v2-badge-surface: var(--v2-shell-role-surface);
    --v2-badge-text: var(--v2-shell-sidebar-text);
    --v2-badge-font-size: calc(var(--v2-font-size-body) + var(--v2-border-width));
    --v2-badge-font-weight: var(--v2-font-weight-bold);
    border: var(--v2-border-width) solid var(--v2-shell-role-border);
    letter-spacing: var(--v2-letter-spacing-wide);
  }

  .v2-shell__admin-link {
    display: block;
    margin-top: var(--v2-space-1);
    color: var(--v2-shell-link-text);
    font-size: var(--v2-font-size-caption);
    line-height: var(--v2-line-height-caption);
    text-decoration: none;
  }

  .v2-shell__admin-link:hover {
    color: var(--v2-shell-link-text-hover);
  }

  .v2-shell__main {
    position: relative;
    z-index: var(--v2-z-base);
    min-width: 0;
    background: transparent;
  }

  .v2-shell__topbar {
    position: sticky;
    top: 0;
    z-index: var(--v2-z-sticky);
    min-height: var(--v2-topbar-height);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--v2-space-5);
    color: var(--v2-topbar-text);
    background: var(--v2-shell-topbar-surface);
    border-bottom: var(--v2-border-width) solid var(--v2-shell-topbar-border);
  }

  .v2-shell__topbar h2 {
    margin: 0;
    color: var(--v2-topbar-text);
    font-family: var(--v2-font-family-sans);
    font-size: calc(var(--v2-font-size-section) + var(--v2-space-micro));
    font-weight: var(--v2-font-weight-semibold);
    line-height: var(--v2-line-height-heading);
    letter-spacing: calc(var(--v2-letter-spacing-wide) / 2);
  }

  .v2-shell__topbar-actions {
    --v2-button-height: calc(var(--v2-control-height-default) - var(--v2-space-micro));
    --v2-button-radius: var(--v2-space-1);
    --v2-button-padding: var(--v2-space-3);
    --v2-button-font-size: calc(var(--v2-font-size-caption) + var(--v2-border-width));
  }

  .v2-shell__content {
    padding: var(--v2-space-4) var(--v2-space-5);
  }

  @media (max-width: 900px) {
    .v2-shell {
      grid-template-columns: 1fr;
    }

    .v2-shell__sidebar {
      position: sticky;
      top: 0;
      z-index: var(--v2-z-sticky);
    }

    .v2-shell__nav {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .v2-shell__sidebar-foot {
      display: none;
    }
  }

  @media (max-width: 560px) {
    .v2-shell__content,
    .v2-shell__topbar {
      padding-right: calc(var(--v2-space-2) + var(--v2-space-1) - var(--v2-border-width) * 2);
      padding-left: calc(var(--v2-space-2) + var(--v2-space-1) - var(--v2-border-width) * 2);
    }
  }

  .v2-shell {
    grid-template-columns: var(--v2-layout-sidebar) minmax(0, 1fr);
    background: var(--v2-shell-workspace-surface);
  }

  .v2-shell__sidebar {
    position: sticky;
    top: 0;
    z-index: var(--v2-z-sidebar);
    height: 100vh;
    background: var(--v2-shell-sidebar-surface);
    border-right-color: var(--v2-shell-sidebar-divider);
  }

  .v2-shell__brand {
    display: flex;
    min-height: var(--v2-layout-topbar);
    align-items: center;
    gap: var(--v2-space-2);
    padding: 0 var(--v2-space-3);
  }

  .v2-shell__brand-mark {
    display: grid;
    width: 34px;
    height: 34px;
    flex: 0 0 auto;
    place-items: center;
    border: var(--v2-border-width) solid var(--v2-shell-role-border);
    border-radius: var(--v2-radius-sm);
    background: var(--v2-action-primary);
    color: var(--v2-text-inverse);
    font-family: var(--v2-font-family-mono);
    font-size: var(--v2-font-size-caption);
    font-weight: var(--v2-font-weight-bold);
  }

  .v2-shell__brand-copy {
    min-width: 0;
  }

  .v2-shell__brand-copy strong {
    overflow: hidden;
    font-size: calc(var(--v2-font-size-body) + var(--v2-border-width));
    letter-spacing: var(--v2-letter-spacing-normal);
    text-overflow: ellipsis;
  }

  .v2-shell__brand-copy span {
    margin-top: var(--v2-space-micro);
    font-family: var(--v2-font-family-mono);
    font-size: var(--v2-font-size-tiny);
    letter-spacing: var(--v2-letter-spacing-wide);
  }

  .v2-shell__project-context {
    display: grid;
    gap: var(--v2-space-1);
    padding: var(--v2-space-3);
    border-bottom: var(--v2-border-width) solid var(--v2-shell-sidebar-divider);
  }

  .v2-shell__context-label,
  .v2-shell__nav-heading {
    color: var(--v2-shell-sidebar-text-muted);
    font-size: var(--v2-font-size-tiny);
    font-weight: var(--v2-font-weight-semibold);
    letter-spacing: var(--v2-letter-spacing-wide);
    text-transform: uppercase;
  }

  .v2-shell__project-card {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    padding: var(--v2-space-micro) var(--v2-space-1) var(--v2-space-micro) var(--v2-space-3);
    border: var(--v2-border-width) solid var(--v2-shell-sidebar-divider);
    border-radius: var(--v2-radius-sm);
    background: var(--v2-shell-sidebar-item-hover);
  }

  .v2-shell__project-dot {
    width: var(--v2-space-1);
    height: var(--v2-space-1);
    border-radius: var(--v2-radius-round);
    background: var(--v2-feedback-success);
  }

  .v2-shell__project-select {
    --v2-select-surface: transparent;
    --v2-select-text: var(--v2-shell-sidebar-text);
    --v2-select-border: transparent;
    --v2-select-border-hover: var(--v2-shell-role-border);
    --v2-select-border-focus: var(--v2-shell-sidebar-item-indicator);
  }

  .v2-shell__project-card :deep(.v2-shell__project-select) {
    width: 100%;
    min-width: 0;
    padding-left: var(--v2-space-2);
    border-color: transparent;
    background: transparent;
    color: var(--v2-shell-sidebar-text);
    color-scheme: dark;
    font-weight: var(--v2-font-weight-medium);
  }

  .v2-shell__project-card :deep(.v2-shell__project-select:hover:not(:disabled)) {
    border-color: transparent;
  }

  .v2-shell__project-card :deep(.v2-shell__project-select option) {
    background: var(--v2-shell-sidebar-surface);
    color: var(--v2-shell-sidebar-text);
  }

  .v2-shell__nav {
    display: block;
    overflow-y: auto;
    padding: var(--v2-space-2);
    scrollbar-width: none;
  }

  .v2-shell__nav::-webkit-scrollbar {
    width: 0;
    height: 0;
  }

  .v2-shell__nav-group + .v2-shell__nav-group {
    margin-top: var(--v2-space-3);
  }

  .v2-shell__nav-heading {
    margin: 0;
    padding: 0 var(--v2-space-2) var(--v2-space-1);
  }

  .v2-shell__nav-button {
    --v2-button-height: var(--v2-control-height-default);
    --v2-button-radius: var(--v2-radius-sm);
    --v2-button-padding: var(--v2-space-2);
    --v2-button-font-size: var(--v2-font-size-body);
    position: relative;
    gap: var(--v2-space-2);
    margin-bottom: var(--v2-space-micro);
    letter-spacing: var(--v2-letter-spacing-normal);
  }

  .v2-shell__nav-button::before {
    width: calc(var(--v2-border-width) * 3);
    border-radius: 0;
  }

  .v2-shell__nav-button:hover::before,
  .v2-shell__nav-button--active::before {
    height: calc(100% - var(--v2-space-2));
  }

  .v2-shell__nav-icon {
    width: var(--v2-icon-size-sm);
    height: var(--v2-icon-size-sm);
    flex: 0 0 auto;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.7;
  }

  .v2-shell__nav-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .v2-shell__sidebar-foot {
    padding: var(--v2-space-3);
  }

  .v2-shell__account {
    display: flex;
    align-items: center;
    gap: var(--v2-space-2);
  }

  .v2-shell__avatar {
    display: grid;
    width: var(--v2-control-height-compact);
    height: var(--v2-control-height-compact);
    flex: 0 0 auto;
    place-items: center;
    border-radius: var(--v2-radius-round);
    background: var(--v2-shell-sidebar-item-active);
    color: var(--v2-shell-sidebar-text);
    font-weight: var(--v2-font-weight-bold);
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
    color: var(--v2-shell-sidebar-text);
    font-size: var(--v2-font-size-caption);
  }

  .v2-shell__account-copy small {
    color: var(--v2-shell-sidebar-text-muted);
    font-size: var(--v2-font-size-tiny);
  }

  .v2-shell__role {
    --v2-badge-height: var(--v2-icon-size-md);
    --v2-badge-padding: var(--v2-space-1);
    --v2-badge-font-size: var(--v2-font-size-tiny);
  }

  .v2-shell__admin-links {
    display: flex;
    gap: var(--v2-space-2);
    margin-top: var(--v2-space-2);
  }

  .v2-shell__admin-link {
    margin-top: 0;
  }

  .v2-shell__main {
    background: var(--v2-shell-workspace-surface);
  }

  .v2-shell__topbar {
    min-height: var(--v2-layout-topbar);
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--v2-space-3);
    padding: 0 var(--v2-space-4);
  }

  .v2-shell__topbar-leading,
  .v2-shell__topbar-actions,
  .v2-shell__breadcrumb {
    display: flex;
    align-items: center;
  }

  .v2-shell__topbar-leading,
  .v2-shell__topbar-actions {
    gap: var(--v2-space-2);
  }

  .v2-shell__topbar-actions {
    justify-content: flex-end;
  }

  .v2-shell__breadcrumb {
    min-width: 0;
    gap: var(--v2-space-1);
    color: var(--v2-text-muted);
    font-size: var(--v2-font-size-caption);
  }

  .v2-shell__breadcrumb h1 {
    margin: 0;
    overflow: hidden;
    color: var(--v2-text-primary);
    font-size: var(--v2-font-size-body);
    font-weight: var(--v2-font-weight-semibold);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .v2-shell__drawer-trigger:focus-visible,
  .v2-shell__drawer-close:focus-visible {
    outline: 0;
    box-shadow: var(--v2-state-focus-ring);
  }

  .v2-shell__icon-action {
    display: inline-grid;
    width: var(--v2-control-height-compact);
    height: var(--v2-control-height-compact);
    flex: 0 0 auto;
    place-items: center;
    padding: 0;
    border: var(--v2-border-width) solid var(--v2-border-panel);
    border-radius: var(--v2-radius-round);
    background: var(--v2-surface-default);
    color: var(--v2-text-secondary);
    cursor: pointer;
    font-size: var(--v2-font-size-caption);
    font-weight: var(--v2-font-weight-semibold);
  }

  .v2-shell__icon-action:hover {
    border-color: var(--v2-border-focus);
    color: var(--v2-action-primary);
  }

  .v2-shell__icon-action:focus-visible {
    outline: 0;
    box-shadow: var(--v2-state-focus-ring);
  }

  .v2-shell__icon-action svg {
    width: var(--v2-icon-size-sm);
    height: var(--v2-icon-size-sm);
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .v2-shell__icon-action--account {
    border-color: var(--v2-action-primary);
    background: var(--v2-action-primary);
    color: var(--v2-text-inverse);
  }

  .v2-shell__content {
    padding: var(--v2-space-4);
  }

  .v2-shell__drawer-trigger,
  .v2-shell__drawer-close,
  .v2-shell__backdrop {
    display: none;
  }

  @media (max-width: 1080px) {
    .v2-shell {
      grid-template-columns: minmax(0, 1fr);
    }

    .v2-shell__sidebar {
      position: fixed;
      left: 0;
      transform: translateX(-100%);
      transition: transform var(--v2-motion-duration-dialog) var(--v2-motion-easing-standard);
    }

    .v2-shell__sidebar--open {
      transform: translateX(0);
    }

    .v2-shell__backdrop {
      position: fixed;
      z-index: calc(var(--v2-z-sidebar) - 1);
      inset: 0;
      display: block;
      width: 100%;
      height: 100%;
      padding: 0;
      border: 0;
      background: var(--v2-surface-overlay);
    }

    .v2-shell__drawer-trigger,
    .v2-shell__drawer-close {
      display: inline-grid;
      width: var(--v2-control-height-compact);
      height: var(--v2-control-height-compact);
      flex: 0 0 auto;
      place-items: center;
      border: 0;
      border-radius: var(--v2-radius-sm);
      background: transparent;
      color: inherit;
      cursor: pointer;
      font-size: var(--v2-font-size-section);
    }

    .v2-shell__drawer-close {
      margin-left: auto;
      color: var(--v2-shell-sidebar-text-muted);
    }

    .v2-shell__sidebar-foot {
      display: block;
    }

    .v2-shell__nav {
      display: block;
    }

    .v2-shell__topbar {
      grid-template-columns: minmax(0, 1fr) auto;
      padding: 0 var(--v2-space-3);
    }
  }

  @media (max-width: 720px) {
    .v2-shell__topbar {
      grid-template-columns: minmax(0, 1fr) auto;
      gap: var(--v2-space-2);
    }

    .v2-shell__breadcrumb > span {
      display: none;
    }

    .v2-shell__icon-action:first-of-type {
      display: none;
    }

    .v2-shell__content {
      padding: var(--v2-space-3);
    }
  }

  /* A3 shell parity: pure-text navigation and prototype-matched spacing. */
  .v2-shell {
    grid-template-columns: var(--v2-shell-sidebar-width) minmax(0, 1fr);
  }

  .v2-shell__sidebar::before {
    position: absolute;
    z-index: calc(var(--v2-z-sidebar) + 1);
    top: 0;
    right: 0;
    left: 0;
    height: 4px;
    background: var(--v2-action-primary);
    content: "";
  }

  .v2-shell__sidebar {
    font-family: var(--v2-font-family-sans);
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }

  .v2-shell__brand {
    min-height: 72px;
    padding: 0 24px;
    background: var(--v2-surface-context);
  }

  .v2-shell__brand-mark,
  .v2-shell__nav-icon,
  .v2-shell__avatar {
    display: none;
  }

  .v2-shell__brand-copy strong {
    font-family: var(--v2-font-family-sans);
    font-size: 16px;
    font-weight: var(--v2-font-weight-bold);
    letter-spacing: 0;
  }

  .v2-shell__brand-copy span {
    margin-top: 5px;
    color: var(--v2-text-muted);
    font-size: var(--v2-font-size-caption);
    letter-spacing: 0.12em;
  }

  .v2-shell__project-context {
    gap: 6px;
    padding: 19px 24px 17px;
    background: var(--v2-shell-sidebar-surface);
  }

  .v2-shell__project-card {
    min-height: 34px;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
  }

  .v2-shell__project-card :deep(.v2-shell__project-select) {
    padding-right: 16px;
    padding-left: 8px;
    color-scheme: light;
  }

  .v2-shell__nav {
    padding: 16px 0;
  }

  .v2-shell__nav-group + .v2-shell__nav-group {
    margin-top: 18px;
  }

  .v2-shell__nav-heading {
    padding: 0 24px 7px;
    color: var(--v2-text-muted);
    font-size: 11px;
    font-weight: var(--v2-font-weight-semibold);
    letter-spacing: 0;
  }

  .v2-shell__nav-button {
    --v2-button-height: 38px;
    --v2-button-radius: 0;
    --v2-button-padding: 24px;
    --v2-button-font-size: 14px;
    --v2-button-font-weight: var(--v2-font-weight-medium);
    gap: 0;
    margin-bottom: 0;
    color: var(--v2-shell-sidebar-text);
  }

  .v2-shell__nav-button--active {
    --v2-button-ghost-bg: var(--v2-shell-sidebar-item-active);
    --v2-button-ghost-text: var(--v2-action-primary);
    --v2-button-font-weight: var(--v2-font-weight-semibold);
  }

  .v2-shell__nav-button::before {
    width: 3px;
  }

  .v2-shell__nav-button:hover::before,
  .v2-shell__nav-button--active::before {
    height: 21px;
  }

  .v2-shell__nav-button--active::after {
    content: none;
  }

  .v2-shell__sidebar-foot {
    padding: 18px 24px;
    background: var(--v2-shell-sidebar-surface);
  }

  .v2-shell__account {
    gap: 0;
  }

  .v2-shell__topbar {
    min-height: var(--v2-shell-topbar-height);
    padding: 0 28px;
    background: var(--v2-shell-topbar-surface);
  }

  .v2-shell__content {
    padding: 24px 28px 40px;
  }

  .v2-shell__content > * {
    width: 100%;
    max-width: var(--v2-layout-workspace-max);
    margin-inline: auto;
  }

  @media (max-width: 1080px) {
    .v2-shell {
      grid-template-columns: minmax(0, 1fr);
    }

    .v2-shell__brand {
      padding: 0 var(--v2-space-3);
    }

    .v2-shell__content {
      padding: 22px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .v2-shell__sidebar {
      transition-duration: var(--v2-motion-reduced);
    }
  }
</style>
