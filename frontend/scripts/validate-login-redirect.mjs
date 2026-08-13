import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const navigationPath = resolve(scriptDir, '../src/services/navigation.js')
const navigationSource = readFileSync(navigationPath, 'utf8')

function extractAsyncFunction(source, name) {
  const signature = `export async function ${name}`
  const start = source.indexOf(signature)
  assert.notEqual(start, -1, `未找到 ${signature}`)

  const openingBrace = source.indexOf('{', start)
  let depth = 0
  let closingBrace = -1
  for (let index = openingBrace; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1
    if (source[index] === '}') depth -= 1
    if (depth === 0) {
      closingBrace = index
      break
    }
  }
  assert.notEqual(closingBrace, -1, `${name} 缺少结束大括号`)

  return source
    .slice(start, closingBrace + 1)
    .replace(/^export\s+/, '')
}

const functionSource = extractAsyncFunction(navigationSource, 'navigateAfterLogin')
const viewFunctionSource = extractAsyncFunction(navigationSource, 'navigateToView')

function createHarness({ migrated = ['dashboard', 'apiCases'], initiallyLoaded = true } = {}) {
  const pushes = []
  let loaded = initiallyLoaded
  let loadCalls = 0
  const knownPaths = new Set([
    '/',
    '/login',
    '/dashboard',
    '/api-cases',
    '/projects',
    '/records',
    '/ui-cases',
    '/users',
    '/requirementVerification',
  ])
  const router = {
    push(target) {
      pushes.push(target)
      return Promise.resolve()
    },
    resolve(target) {
      const raw = typeof target === 'string' ? target : target.path
      const path = raw.split(/[?#]/, 1)[0]
      const viewKey = path === '/requirementVerification' ? 'requirementVerification' : path === '/api-cases' ? 'apiCases' : null
      return { matched: knownPaths.has(path) ? [{ name: viewKey || path, meta: viewKey ? { viewKey } : {} }] : [{ meta: {} }] }
    },
  }
  const browserWindow = { location: { href: 'about:blank' } }
  const factory = new Function(
    'router',
    'window',
    'isMigrationConfigLoaded',
    'loadMigrationConfig',
    'getMigratedList',
    'isMigrated',
    `const LEGACY_APP_BASE = '/'; const LEGACY_HASH_BASE = '/#/'; ${functionSource}; return navigateAfterLogin;`,
  )
  const navigateAfterLogin = factory(
    router,
    browserWindow,
    () => loaded,
    async () => { loadCalls += 1; loaded = true },
    () => migrated,
    (key) => migrated.includes(key),
  )
  return { navigateAfterLogin, pushes, browserWindow, get loadCalls() { return loadCalls } }
}

function createViewHarness({ migrated = [], knownRouteNames = ['systemRegression'] } = {}) {
  const pushes = []
  const router = {
    push(target) {
      pushes.push(target)
      return Promise.resolve()
    },
    hasRoute(name) {
      return knownRouteNames.includes(name)
    },
  }
  const browserWindow = { location: { href: 'about:blank' } }
  const factory = new Function(
    'router',
    'window',
    'isMigrated',
    'isMigrationConfigLoaded',
    'loadMigrationConfig',
    `const LEGACY_HASH_BASE = '/#/';
     const LEGACY_STATIC_VIEW_ALIASES = {
       functionalTests: 'requirementVerification',
       caseGeneration: 'requirementVerification',
     };
     ${viewFunctionSource};
     return navigateToView;`,
  )
  const navigateToView = factory(
    router,
    browserWindow,
    (key) => migrated.includes(key),
    () => true,
    async () => {},
  )
  return { navigateToView, pushes, browserWindow }
}

async function expectVueRedirect(redirect, expected) {
  const harness = createHarness()
  await harness.navigateAfterLogin(redirect)
  assert.deepEqual(harness.pushes, [expected])
  assert.equal(harness.browserWindow.location.href, 'about:blank')
}

const cases = [
  {
    name: 'V3 未知路径交给 Vue catch-all 恢复到工作台',
    run: async () => {
      const harness = createHarness()
      await harness.navigateAfterLogin('/v3/not-exist')
      assert.deepEqual(harness.pushes, ['/not-exist'])
      assert.equal(harness.browserWindow.location.href, 'about:blank')
    },
  },
  {
    name: '登录回跳等待迁移配置加载后再决定 Vue 页面',
    run: async () => {
      const harness = createHarness({ migrated: ['apiCases'], initiallyLoaded: false })
      await harness.navigateAfterLogin('/v3/api-cases')
      assert.equal(harness.loadCalls, 1)
      assert.deepEqual(harness.pushes, ['/api-cases'])
      assert.equal(harness.browserWindow.location.href, 'about:blank')
    },
  },
  {
    name: '登录回跳到未迁移需求验证时进入完整旧版',
    run: async () => {
      const harness = createHarness()
      await harness.navigateAfterLogin('/v3/requirementVerification')
      assert.deepEqual(harness.pushes, [])
      assert.equal(harness.browserWindow.location.href, '/#/requirementVerification')
    },
  },
  {
    name: '系统回归未迁移时即使存在 Vue 路由也回到旧版',
    run: async () => {
      const harness = createViewHarness()
      await harness.navigateToView('systemRegression')
      assert.deepEqual(harness.pushes, [])
      assert.equal(harness.browserWindow.location.href, '/#/systemRegression')
    },
  },
  {
    name: 'Router Guard 生成的 dashboard 内部路径交给 Vue Router',
    run: () => expectVueRedirect('/dashboard', '/dashboard'),
  },
  {
    name: 'Router Guard 生成的 api-cases 内部路径交给 Vue Router',
    run: () => expectVueRedirect('/api-cases', '/api-cases'),
  },
  {
    name: 'Vue 内部路径保留 query 和 hash',
    run: () => expectVueRedirect('/api-cases?project_id=3#case-8', '/api-cases?project_id=3#case-8'),
  },
  {
    name: '已有 /v3 前缀不会重复添加 base',
    run: () => expectVueRedirect('/v3/api-cases?project_id=3#case-8', '/api-cases?project_id=3#case-8'),
  },
  {
    name: '无 redirect 时保持现有默认首页行为',
    run: async () => {
      const harness = createHarness()
      await harness.navigateAfterLogin()
      assert.deepEqual(harness.pushes, [{ name: 'dashboard' }])
      assert.equal(harness.browserWindow.location.href, 'about:blank')
    },
  },
  {
    name: 'legacy hash 目标保持浏览器跨应用跳转',
    run: async () => {
      const harness = createHarness()
      await harness.navigateAfterLogin('/#/dataScripts')
      assert.deepEqual(harness.pushes, [])
      assert.equal(harness.browserWindow.location.href, '/#/dataScripts')
    },
  },
  {
    name: '普通非 Vue 目标保持浏览器跨应用跳转',
    run: async () => {
      const harness = createHarness()
      await harness.navigateAfterLogin('/legacy-path')
      assert.deepEqual(harness.pushes, [])
      assert.equal(harness.browserWindow.location.href, '/legacy-path')
    },
  },
  {
    name: '带 /v3 前缀的未知目标交给 Vue catch-all',
    run: async () => {
      const harness = createHarness()
      await harness.navigateAfterLogin('/v3/legacy-path')
      assert.deepEqual(harness.pushes, ['/legacy-path'])
      assert.equal(harness.browserWindow.location.href, 'about:blank')
    },
  },
  {
    name: '带 /v3 前缀的 legacy hash 目标不交给 Vue Router',
    run: async () => {
      const harness = createHarness()
      await harness.navigateAfterLogin('/v3/#/dataScripts')
      assert.deepEqual(harness.pushes, [])
      assert.equal(harness.browserWindow.location.href, '/v3/#/dataScripts')
    },
  },
]

const failures = []
for (const testCase of cases) {
  try {
    await testCase.run()
    console.log(`PASS ${testCase.name}`)
  } catch (error) {
    failures.push({ name: testCase.name, error })
    console.error(`FAIL ${testCase.name}`)
    console.error(`  ${error.message}`)
  }
}

if (failures.length > 0) {
  console.error(`Login redirect validation failed: ${failures.length}/${cases.length} cases failed.`)
  process.exit(1)
}

console.log(`Login redirect validation passed: ${cases.length}/${cases.length} cases passed.`)
