/**
 * 统一导航服务
 *
 * 职责：根据 migration-config.json 统一决定页面跳转方式
 * - 已迁移页面 → Vue Router（应用内跳转）
 * - 未迁移页面 → 旧应用（window.location.href）
 *
 * 所有页面统一使用本模块，不直接调用 window.location.href。
 * LoginView 登录成功后、AppShell 侧边栏导航、Router 守卫
 * 均通过本模块决策。
 *
 * 依赖：
 * - migration.js 提供迁移配置查询
 * - router/index.js 提供 Vue Router 实例
 */
import router from '../router/index.js'
import {
  isMigrated,
  isMigrationConfigLoaded,
  loadMigrationConfig,
  getMigratedList,
} from './migration.js'

const LEGACY_APP_BASE = '/'
const LEGACY_HASH_BASE = '/#/'

/**
 * 跳转到指定视图
 * - 已迁移 → Vue Router
 * - 未迁移 → 旧应用 /#/<viewKey>
 * @param {string} viewKey - 视图 key（如 dashboard / projects / records）
 */
export async function navigateToView(viewKey) {
  if (!isMigrationConfigLoaded()) {
    await loadMigrationConfig()
  }
  if (isMigrated(viewKey)) {
    router.push({ name: viewKey })
  } else {
    window.location.href = LEGACY_HASH_BASE + viewKey
  }
}

/**
 * 登录成功后的统一跳转
 * - 有 redirect 参数：
 *   - /v3/xxx → Vue Router 内部跳转
 *   - 其他 → 旧应用路径
 * - 无 redirect → 跳首页
 *   - 已迁移页面存在时跳第一个已迁移页面
 *   - 无已迁移页面时跳旧应用首页
 * @param {string} [redirect] - 登录后回跳路径
 */
export async function navigateAfterLogin(redirect) {
  if (redirect && typeof redirect === 'string') {
    if (redirect.startsWith('/v3')) {
      // Vue3 内部路由，去掉 /v3 前缀
      const path = redirect.replace(/^\/v3/, '') || '/'
      router.push(path)
    } else {
      // 旧应用路径
      window.location.href = redirect
    }
    return
  }

  // 无 redirect，跳首页
  if (!isMigrationConfigLoaded()) {
    await loadMigrationConfig()
  }

  // 已迁移页面存在时跳第一个已迁移页面
  const list = getMigratedList()
  if (list.length > 0) {
    router.push({ name: list[0] })
    return
  }

  // 无已迁移页面，跳旧应用首页
  window.location.href = LEGACY_APP_BASE
}

/**
 * 退出登录后跳转
 */
export function navigateAfterLogout() {
  router.push('/login')
}
