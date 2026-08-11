import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(resolve(scriptDir, '..'), 'src', 'views', 'DashboardView.vue'), 'utf8')
const failures = []
const requirePattern = (pattern, message) => { if (!pattern.test(source)) failures.push(message) }

requirePattern(/getDashboard/, 'dashboard summary API must remain')
requirePattern(/listRecords/, 'dashboard must load real records for trend aggregation')
requirePattern(/pageSize:\s*200/, 'dashboard must cap trend input at 200 records')
requirePattern(/WorkbenchPageHeader/, 'dashboard must use the workbench page header')
requirePattern(/WorkbenchMetricRail/, 'dashboard must use the metric rail')
requirePattern(/WorkbenchTrendChart/, 'dashboard must render the SVG trend chart')
requirePattern(/WorkbenchAttentionList/, 'dashboard must render a derived attention list')
requirePattern(/BaseErrorState/, 'dashboard must render an error state')
requirePattern(/BaseSkeleton/, 'dashboard must retain a loading state')
requirePattern(/BaseEmptyState/, 'dashboard must retain an empty state')
requirePattern(/app\.filters\.projectId/, 'dashboard must preserve the shared project filter')
requirePattern(/openProtectedFile/, 'dashboard must retain protected report and screenshot actions')
requirePattern(/showLog/, 'dashboard must retain the log action')
requirePattern(/execute_time/, 'trend aggregation must use record timestamps')
requirePattern(/result/, 'trend aggregation must derive passed and failed states')
if (/const\s+\w*Trend\w*\s*=\s*\{\s*labels:\s*\[[^\]]+\]/s.test(source)) failures.push('dashboard contains hard-coded trend data')

if (failures.length) {
  console.error(`V3 dashboard contract validation failed (${failures.length})`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V3 dashboard contract validation passed')
