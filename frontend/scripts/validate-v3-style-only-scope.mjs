import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(fileURLToPath(new URL('../..', import.meta.url)))
const normalizePath = (value) => value.replaceAll('\\', '/')
const normalizeText = (value) => value.replaceAll('\r\n', '\n')
const runGit = (...args) => execFileSync('git', ['-c', 'core.quotepath=false', ...args], { cwd: repoRoot, encoding: 'utf8' }).trim()

const cssAllowlist = new Set([
  'frontend/src/styles/v2/tokens.foundation.css',
  'frontend/src/styles/v2/tokens.semantic.css',
  'frontend/src/styles/v2/tokens.component.css',
  'frontend/src/styles/v2/base.css',
  'static/design-tokens.css',
  'static/design-system-base.css',
  'static/login.css',
  'static/styles.css',
  'static/system-regression.css',
])

// Presentation layer：允许调整 Vue <template> 的纯展示结构，
// 但 <script> 必须与 HEAD 逐字一致（业务逻辑不变）。
const presentationScopeAllowlist = new Set([
  'frontend/src/components/AppShell.vue',
  'frontend/src/components/AiConfigDialog.vue',
  'frontend/src/components/AppModal.vue',
  'frontend/src/components/AppTable.vue',
  'frontend/src/components/v2/base/BaseModal.vue',
  'frontend/src/components/AppFormDialog.vue',
  'frontend/src/components/v2/workbench/WorkbenchPageHeader.vue',
  'frontend/src/components/v2/workbench/WorkbenchPanel.vue',
  'frontend/src/views/ApiCasesView.vue',
  'frontend/src/views/DashboardView.vue',
  'frontend/src/views/ProjectsView.vue',
  'frontend/src/views/RecordsView.vue',
  'frontend/src/views/RequirementVerificationView.vue',
  'frontend/src/views/UiCasesView.vue',
  'frontend/src/views/UsersView.vue',
])

const styleOnlyAllowlist = new Set([
  'frontend/src/components/AiConfigDialog.vue',
  'frontend/src/components/AppFormDialog.vue',
  'frontend/src/components/AppModal.vue',
  'frontend/src/components/AppPagination.vue',
  'frontend/src/components/AppShell.vue',
  'frontend/src/components/AppTable.vue',
  'frontend/src/components/ui-cases/UiCaseForm.vue',
  'frontend/src/components/ui-cases/UiExecutionPanel.vue',
  'frontend/src/components/ui-cases/UiRecordingPanel.vue',
  'frontend/src/components/v2/base/BaseBadge.vue',
  'frontend/src/components/v2/base/BaseButton.vue',
  'frontend/src/components/v2/base/BaseCard.vue',
  'frontend/src/components/v2/base/BaseCheckbox.vue',
  'frontend/src/components/v2/base/BaseChip.vue',
  'frontend/src/components/v2/base/BaseDropdown.vue',
  'frontend/src/components/v2/base/BaseDropdownItem.vue',
  'frontend/src/components/v2/base/BaseEmptyState.vue',
  'frontend/src/components/v2/base/BaseErrorState.vue',
  'frontend/src/components/v2/base/BaseIconButton.vue',
  'frontend/src/components/v2/base/BaseInput.vue',
  'frontend/src/components/v2/base/BaseModal.vue',
  'frontend/src/components/v2/base/BasePagination.vue',
  'frontend/src/components/v2/base/BaseSelect.vue',
  'frontend/src/components/v2/base/BaseSkeleton.vue',
  'frontend/src/components/v2/base/BaseTable.vue',
  'frontend/src/components/v2/base/BaseTextarea.vue',
  'frontend/src/components/v2/base/BaseTooltip.vue',
  'frontend/src/components/v2/workbench/WorkbenchAttentionList.vue',
  'frontend/src/components/v2/workbench/WorkbenchMetricRail.vue',
  'frontend/src/components/v2/workbench/WorkbenchPageHeader.vue',
  'frontend/src/components/v2/workbench/WorkbenchPanel.vue',
  'frontend/src/components/v2/workbench/WorkbenchStatus.vue',
  'frontend/src/components/v2/workbench/WorkbenchTrendChart.vue',
  'frontend/src/views/ApiCasesView.vue',
  'frontend/src/views/DashboardView.vue',
  'frontend/src/views/ProjectsView.vue',
  'frontend/src/views/RecordsView.vue',
  'frontend/src/views/RequirementVerificationView.vue',
  'frontend/src/views/UiCasesView.vue',
  'frontend/src/views/UsersView.vue',
  'static/admin/heal-logs.html',
  'static/admin/templates.html',
])

const supportPrefixes = [
  '.pytest_cache/',
  'ui-reference/',
  'ui-prototype/',
  'tests/test_permissions.py',
  'docs/ui-redesign/',
  'docs/frontend-v3-ui-functional-fingerprint.md',
  'docs/frontend-v3-ui-functional-fingerprint-after.md',
  'docs/frontend-v3-grok-ui-functional-fingerprint-before.md',
  'docs/frontend-v3-grok-ui-functional-fingerprint-after.md',
  'docs/frontend-v3-cursor-grok-functional-fingerprint-before.md',
  'docs/frontend-v3-cursor-grok-functional-fingerprint-after.md',
  'docs/superpowers/plans/',
  'docs/superpowers/plans/2026-08-12-art-design-pro-ui-pilot.md',
  'docs/frontend-v2/ui-pilot-screenshots/',
  'docs/frontend-v2/full-system-screenshots/',
  'docs/frontend-v2/phase-reports/frontend-v3-art-design-pro-ui-pilot-report-2026-08-12.md',
  'docs/frontend-v2/phase-reports/frontend-v3-art-design-pro-source-pilot-report-2026-08-12.md',
  'docs/frontend-v2/phase-reports/frontend-v3-light-workbench-redesign-2026-08-11.md',
  'docs/frontend-v2/handoff/CURRENT-TASK.md',
  'docs/frontend-v2/handoff/STATE.json',
  'frontend/scripts/validate-v3-light-visual-contract.mjs',
  'frontend/scripts/validate-v3-style-only-scope.mjs',
  'frontend/scripts/validate-v3-visual-contract.mjs',
]

const cacheEntryAllowlist = new Set([
  'frontend/index.html',
  'static/index.html',
  '启动服务.bat',
])

const entryGuardAllowlist = new Set([
  'frontend/src/App.vue',
])

const CACHE_VERSION = '20260812-v3-enterprise-3'

function normalizeVisualAssetVersions(source) {
  let normalized = source
  for (const asset of ['styles.css', 'design-tokens.css', 'design-system-base.css', 'login.css', 'system-regression.css']) {
    normalized = normalized.replace(
      new RegExp(`href="/static/${asset.replace('.', '\\.') }\\?v=[^"]+"`, 'g'),
      `href="/static/${asset}?v=__CACHE_VERSION__"`,
    )
  }
  return normalized
}

function stripStyles(source) {
  return normalizeVisualAssetVersions(normalizeText(source).replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ''))
}

function stripPresentation(source) {
  const normalized = normalizeText(source)
  const scripts = [...normalized.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)]
    .map((match) => match[1])
    .join('\n')
  return scripts
}

function fromHead(path) {
  return execFileSync('git', ['show', `HEAD:${path}`], { cwd: repoRoot, encoding: 'utf8' })
}

function normalizeCacheEntry(path, source) {
  let normalized = normalizeText(source)
  if (path === 'frontend/index.html' || path === 'static/index.html') {
    normalized = normalizeVisualAssetVersions(normalized)
  }
  if (path === '启动服务.bat') {
    normalized = normalized
      .replace(/^echo   Auto Test Platform.*$/m, 'echo   Auto Test Platform __ENTRY_TITLE__')
      .replace(/^echo   URL: http:\/\/127\.0\.0\.1:8000\/.*$/m, 'echo   URL: __ENTRY_URL__')
      .replace('    rem Wait until the API is ready, then open the cache-busted V3 login page.\n', '')
      .replace(/^    start "" \/b powershell\.exe -NoProfile -WindowStyle Hidden -Command "\$url='http:\/\/127\.0\.0\.1:8000\/v3\/login\?ui=[^']+'; for\(\$i=0; \$i -lt 40; \$i\+\+\)\{ try \{ Invoke-WebRequest 'http:\/\/127\.0\.0\.1:8000\/health' -UseBasicParsing -TimeoutSec 1 \| Out-Null; Start-Process \$url; break \} catch \{ Start-Sleep -Milliseconds 500 \} \}"\n?/m, '')
  }
  return normalized
}

function normalizeEntryGuard(path, source) {
  let normalized = normalizeText(source)
  if (path === 'frontend/src/App.vue') {
    normalized = normalized
      .replace(
        '  <AppShell v-if="routeReady && !route.meta.public" />\n  <router-view v-else-if="routeReady" />',
        '  <AppShell v-if="!route.meta.public" />\n  <router-view v-else />',
      )
      .replace("import { computed } from 'vue'\n", '')
      .replace('const routeReady = computed(() => route.matched.length > 0)\n', '')
  }
  return normalized
}

const changed = new Set()
for (const command of [
  ['diff', '--name-only', '--diff-filter=ACMRTUXB', 'HEAD'],
  ['ls-files', '--others', '--exclude-standard'],
]) {
  const output = runGit(...command)
  if (!output) continue
  for (const path of output.split(/\r?\n/)) changed.add(normalizePath(path))
}

const issues = []
for (const path of [...changed].sort()) {
  if (cssAllowlist.has(path)) continue

  if (presentationScopeAllowlist.has(path)) {
    const absolute = resolve(repoRoot, path)
    if (!existsSync(absolute)) {
      issues.push(`${path}: approved presentation file was deleted`)
      continue
    }
    const currentScript = stripPresentation(readFileSync(absolute, 'utf8'))
    const headScript = stripPresentation(fromHead(path))
    if (currentScript !== headScript) {
      issues.push(`${path}: script changed outside the approved presentation layer`)
    }
    continue
  }

  if (styleOnlyAllowlist.has(path)) {
    const absolute = resolve(repoRoot, path)
    if (!existsSync(absolute)) {
      issues.push(`${path}: approved style-only file was deleted`)
      continue
    }
    const currentFunctional = stripStyles(readFileSync(absolute, 'utf8'))
    const headFunctional = stripStyles(fromHead(path))
    if (currentFunctional !== headFunctional) issues.push(`${path}: template/script/DOM changed outside <style>`)
    continue
  }

  if (cacheEntryAllowlist.has(path)) {
    const absolute = resolve(repoRoot, path)
    const current = readFileSync(absolute, 'utf8')
    if (normalizeCacheEntry(path, current) !== normalizeCacheEntry(path, fromHead(path))) {
      issues.push(`${path}: changed outside the approved cache-bust/entry lines`)
      continue
    }
    if ((path === 'frontend/index.html' || path === 'static/index.html') && ![
      `styles.css?v=${CACHE_VERSION}`,
      `design-tokens.css?v=${CACHE_VERSION}`,
      `design-system-base.css?v=${CACHE_VERSION}`,
      `login.css?v=${CACHE_VERSION}`,
    ].every((value) => current.includes(value))) {
      issues.push(`${path}: active V3 cache-bust version is missing`)
    }
    if (path === '启动服务.bat' && !current.includes(`URL: http://127.0.0.1:8000/v3/login?ui=${CACHE_VERSION}`)) {
      issues.push(`${path}: V3 cache-busted login entry is missing`)
    }
    if (path === '启动服务.bat' && !current.includes("Start-Process $url")) {
      issues.push(`${path}: automatic V3 browser launch is missing`)
    }
    continue
  }

  if (entryGuardAllowlist.has(path)) {
    const absolute = resolve(repoRoot, path)
    const current = readFileSync(absolute, 'utf8')
    if (normalizeEntryGuard(path, current) !== normalizeEntryGuard(path, fromHead(path))) {
      issues.push(`${path}: changed outside the approved route-ready shell guard`)
      continue
    }
    if (!current.includes('routeReady && !route.meta.public') || !current.includes('route.matched.length > 0')) {
      issues.push(`${path}: route-ready shell guard is missing`)
    }
    continue
  }

  if (supportPrefixes.some((prefix) => path === prefix || path.startsWith(prefix))) continue
  issues.push(`${path}: changed outside the approved visual-only allowlist`)
}

const diff = runGit('diff', '--unified=0', 'HEAD', '--', ...[...cssAllowlist, ...styleOnlyAllowlist])
const addedStyleLines = diff
  .split(/\r?\n/)
  .filter((line) => line.startsWith('+') && !line.startsWith('+++'))
  .map((line) => line.slice(1))

const hiddenFunctionPatterns = [
  [/\bdisplay\s*:\s*none\b/i, 'display:none'],
  [/\bvisibility\s*:\s*hidden\b/i, 'visibility:hidden'],
  [/\bopacity\s*:\s*0(?:\D|$)/i, 'opacity:0'],
  [/(?<![\w-])(?:width|height)\s*:\s*0(?:px|rem|em|%|\s|;|$)/i, 'zero size'],
  [/\bpointer-events\s*:\s*none\b/i, 'pointer-events:none'],
]
const responsiveHideSelectors = [
  'v2-shell__drawer-trigger',
  'v2-shell__drawer-close',
  'v2-shell__backdrop',
  'v2-shell__breadcrumb',
]
const unsafeHidingLines = []
let inResponsiveHideBlock = false
for (const line of addedStyleLines) {
  const hasOpenBrace = line.includes('{')
  const hasCloseBrace = line.includes('}')
  if (hasOpenBrace && responsiveHideSelectors.some((selector) => line.includes(selector))) {
    inResponsiveHideBlock = true
  }
  if (inResponsiveHideBlock && hiddenFunctionPatterns.some(([pattern]) => pattern.test(line))) {
    // Known responsive-only hide rules are allowed.
  } else if (!inResponsiveHideBlock && hiddenFunctionPatterns.some(([pattern]) => pattern.test(line))) {
    unsafeHidingLines.push(line)
  }
  if (!hasOpenBrace && hasCloseBrace) {
    inResponsiveHideBlock = false
  }
}
if (unsafeHidingLines.length) {
  issues.push(`added CSS contains forbidden function-hiding pattern: ${unsafeHidingLines.join(' | ')}`)
}

if (issues.length) {
  console.error('V3 UI pilot scope validation failed:')
  for (const issue of issues) console.error(`- ${issue}`)
  process.exit(1)
}

console.log(`V3 UI pilot scope validation passed (${changed.size} changed/untracked paths audited).`)
