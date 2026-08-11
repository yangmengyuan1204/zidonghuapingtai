import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const shell = readFileSync(join(frontendDir, 'src', 'components', 'AppShell.vue'), 'utf8')
const router = readFileSync(join(frontendDir, 'src', 'router', 'index.js'), 'utf8')
const failures = []
const requireSource = (source, pattern, message) => {
  if (!pattern.test(source)) failures.push(message)
}

for (const key of ['dashboard', 'projects', 'apiCases', 'dataScripts', 'requirementVerification', 'uiCases', 'records', 'systemRegression', 'users']) {
  requireSource(router, new RegExp(`key:\\s*['"]${key}['"]`), `menuViews is missing ${key}`)
}
requireSource(router, /key:\s*['"]users['"][^\n]*adminOnly:\s*true/, 'users must remain adminOnly')
requireSource(router, /key:\s*['"]systemRegression['"][^\n]*adminOnly:\s*true/, 'systemRegression must remain adminOnly')
requireSource(shell, /工作空间[\s\S]*测试资产[\s\S]*自动化执行[\s\S]*系统管理/, 'shell must expose four navigation groups')
if (/apiHarvester|ApiHarvester/.test(router) || /apiHarvester|ApiHarvester/.test(shell)) failures.push('retired API harvester is still exposed')
if (/HIDDEN_SIDEBAR_KEYS/.test(shell)) failures.push('shell still contains hidden sidebar keys')
requireSource(shell, /useAppStore/, 'shell must use the existing project store')
requireSource(shell, /fetchProjects\(/, 'shell must load the existing project list')
requireSource(shell, /setProjectId\(/, 'shell project switch must preserve the existing projectId contract')
requireSource(shell, /aria-controls="v2-shell-sidebar"/, 'mobile menu trigger must identify the sidebar')
requireSource(shell, /@keydown\.esc/, 'shell must close the mobile drawer with Escape')
requireSource(shell, /v2-shell__backdrop/, 'shell must provide a dismissible mobile backdrop')
requireSource(shell, /handleLogout/, 'shell must retain logout')
requireSource(shell, /AiConfigDialog/, 'shell must retain the working AI configuration action')
requireSource(shell, /@media \(max-width: 1080px\)/, 'shell mobile drawer breakpoint must be 1080px')
requireSource(shell, /var\(--v2-layout-sidebar\)/, 'shell must consume the locked sidebar width')

if (failures.length) {
  console.error(`V3 shell contract validation failed (${failures.length})`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V3 shell contract validation passed')
