import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8')
const hash = (value) => crypto.createHash('sha256').update(value).digest('hex')
const beforeStyle = (source) => source.replace(/<style[\s\S]*$/, '')

const dashboard = read('src/views/DashboardView.vue')
const shell = read('src/components/AppShell.vue')
const dashboardStyle = dashboard.match(/<style scoped>([\s\S]*)<\/style>/)?.[1] || ''
const failures = []

const frozenRegions = [
  ['Dashboard template/script', beforeStyle(dashboard), '7755d0808d30c3355fec72614759a35fb0e5f9f3fb77aeb2669bbe0845c9c0a7'],
  ['AppShell template/script', beforeStyle(shell), '067a36a4c57792384543a53984cdaa93173c2379c3a9cd923e82911c4d14e179'],
]

for (const [label, source, expected] of frozenRegions) {
  if (hash(source) !== expected) failures.push(`${label} changed; this task is CSS-only`)
}

for (const required of [
  ':deep(.v2-workbench-page-header__title)',
  ':deep(.v2-workbench-metric-rail__intro)',
  ':deep(.v2-workbench-panel__header)',
  ':deep(.v2-workbench-trend-chart__svg)',
  ':deep(.v2-app-table__header)',
  ':deep(.v2-app-table__cell)',
]) {
  if (!dashboardStyle.includes(required)) failures.push(`Dashboard visual calibration missing ${required}`)
}

if (/display\s*:\s*none|visibility\s*:\s*hidden/.test(dashboardStyle)) {
  failures.push('Dashboard CSS must not hide existing functions or data')
}

if (failures.length) {
  console.error('V3 dashboard style-only validation failed:')
  failures.forEach((failure) => console.error(`- ${failure}`))
  process.exit(1)
}

console.log('V3 dashboard style-only validation passed')
