/**
 * 迁移配置服务 — 前端侧唯一迁移配置读取入口
 *
 * 唯一配置源：/static/migration-config.json
 * 与 static/migration-bridge.js 读取同一份配置。
 *
 * 设计要点：
 * - 启动时预加载，后续同步读取已加载结果
 * - 提供 isMigrated(viewKey) 同步查询接口
 * - 加载失败时回退为空集合，不阻塞导航
 *
 * 后续每迁移一个页面，只需修改 migration-config.json，
 * 不需要修改 Router / AppShell / Navigation 源码。
 */
import { ref } from 'vue'

const CONFIG_URL = '/static/migration-config.json'

const migratedSet = ref(new Set())
const loaded = ref(false)
let loadPromise = null

/**
 * 加载迁移配置（幂等，多次调用只发一次请求）
 * @returns {Promise<{migrated: string[]}>}
 */
export function loadMigrationConfig() {
  if (loadPromise) return loadPromise
  loadPromise = fetch(CONFIG_URL)
    .then((res) => res.json())
    .then((config) => {
      migratedSet.value = new Set(config.migrated || [])
      loaded.value = true
      return config
    })
    .catch(() => {
      // 加载失败，回退为空集合，不重定向任何页面
      migratedSet.value = new Set()
      loaded.value = true
      return { migrated: [] }
    })
  return loadPromise
}

/**
 * 同步查询某页面是否已迁移
 * @param {string} viewKey
 * @returns {boolean}
 */
export function isMigrated(viewKey) {
  return migratedSet.value.has(viewKey)
}

/**
 * 获取已迁移页面列表
 * @returns {string[]}
 */
export function getMigratedList() {
  return Array.from(migratedSet.value)
}

/**
 * 配置是否已加载完成
 * @returns {boolean}
 */
export function isMigrationConfigLoaded() {
  return loaded.value
}

// 模块加载时预取配置（不阻塞主线程）
loadMigrationConfig()
