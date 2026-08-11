/**
 * Vue Router 配置
 * base=/v3/，与 FastAPI 挂载路径一致
 *
 * 路由守卫：
 * - 未登录访问需鉴权页面 → 跳 /login
 * - 已登录访问 /login → 跳首页
 *
 * 注：已迁移页面列表由 services/migration.js 读取 migration-config.json 提供，
 *     Router 不再维护 migratedSet。
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

// 菜单配置（与 Static 运行时菜单对齐：需求验证中心已合并 AI用例生成 + 功能验证中心）
// adminOnly 的页面（users）非 admin 不可见
export const menuViews = [
  { key: 'dashboard', label: '工作台总览' },
  { key: 'projects', label: '项目空间' },
  { key: 'apiCases', label: '接口用例库' },
  { key: 'dataScripts', label: '数据工厂' },
  { key: 'requirementVerification', label: '需求验证中心' },
  { key: 'uiCases', label: 'UI自动化' },
  { key: 'records', label: '执行报告' },
  { key: 'systemRegression', label: '系统回归', adminOnly: true },
  { key: 'users', label: '权限中心', adminOnly: true },
]

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    name: 'home',
    // Phase 2A: 首页重定向到已迁移的 dashboard
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { viewKey: 'dashboard' },
  },
  {
    path: '/users',
    name: 'users',
    component: () => import('../views/UsersView.vue'),
    meta: { viewKey: 'users', adminOnly: true },
  },
  {
    path: '/projects',
    name: 'projects',
    component: () => import('../views/ProjectsView.vue'),
    meta: { viewKey: 'projects' },
  },
  {
    path: '/records',
    name: 'records',
    component: () => import('../views/RecordsView.vue'),
    meta: { viewKey: 'records' },
  },
  {
    path: '/api-cases',
    alias: '/apiCases',
    name: 'apiCases',
    component: () => import('../views/ApiCasesView.vue'),
    meta: { viewKey: 'apiCases' },
  },
  {
    path: '/ui-cases',
    alias: '/uiCases',
    name: 'uiCases',
    component: () => import('../views/UiCasesView.vue'),
    meta: { viewKey: 'uiCases' },
  },
  {
    path: '/dataScripts',
    alias: '/data-scripts',
    name: 'dataScripts',
    component: () => import('../views/LegacyEmbedView.vue'),
    meta: { viewKey: 'dataScripts' },
  },
  {
    path: '/requirementVerification',
    alias: '/requirement-verification',
    name: 'requirementVerification',
    component: () => import('../views/RequirementVerificationView.vue'),
    meta: { viewKey: 'requirementVerification' },
  },
  {
    path: '/systemRegression',
    alias: '/system-regression',
    name: 'systemRegression',
    component: () => import('../views/LegacyEmbedView.vue'),
    meta: { viewKey: 'systemRegression', adminOnly: true },
  },
]

const router = createRouter({
  history: createWebHistory('/v3/'),
  routes,
})

// 全局前置守卫
// 职责：
// 1. 公开页面放行（登录页已登录则跳首页）
// 2. 未登录访问受保护页面 → 登录页
// 3. 有 token 但 user 未加载 → 调 fetchMe 恢复（避免刷新后 isAdmin 为 false）
// 4. adminOnly 路由非 admin → 跳 /dashboard
// 注：fetchMe 失败（401/网络）由 API Client 统一处理，此处 try-catch 兜底避免死循环
router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()

  // 公开页面（登录页）直接放行
  if (to.meta.public) {
    // 已登录访问登录页 → 跳首页
    if (auth.isLoggedIn && to.name === 'login') {
      return next('/')
    }
    return next()
  }

  // 需鉴权页面：未登录 → 登录页
  if (!auth.isLoggedIn) {
    return next({ name: 'login', query: { redirect: to.fullPath } })
  }

  // 有 token 但 user 未加载（如刷新后）→ 恢复用户信息
  // 同一次导航只调一次；已有 user 不重复请求
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch (e) {
      // fetchMe 失败：401 由 API Client 跳登录页；其他错误放行，
      // 由 adminOnly 校验决定是否跳 /dashboard，避免无限重定向
      // 若 user 仍为空，adminOnly 路由会被下方逻辑挡住
    }
  }

  // adminOnly 路由：非 admin 不得进入
  if (to.meta.adminOnly && !auth.isAdmin) {
    return next({ path: '/dashboard' })
  }

  next()
})

export default router
