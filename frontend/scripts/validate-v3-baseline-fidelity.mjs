import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8')
const checks = [
  ['src/styles/v2/tokens.foundation.css', ['--v2-layout-workspace-max: none;']],
  ['src/components/AppShell.vue', [
    '质量工作台', 'AI TEST OPERATIONS', '>Q<', '>当前项目</span>',
    '>全局 AI 配置</BaseButton>', '>退出</BaseButton>',
    'AiConfigDialog', ':deep(.v2-shell__project-select option)', 'width: 34px', 'height: 34px',
  ]],
  ['src/views/DashboardView.vue', [
    'title="质量运行概览"', '基于当前项目的真实用例与执行记录，集中查看质量状态、趋势和待处理事项。',
    'WorkbenchPanel title="执行趋势"', 'WorkbenchPanel title="需要关注"',
    '查看执行报告', "navigateToView('records')", "{ key: 'envs'",
    "title: '存在失败待处理'", 'passed: dateKeys.map((date) => days.get(date).passed)',
    'failed: dateKeys.map((date) => days.get(date).failed)',
  ]],
  ['src/components/v2/workbench/WorkbenchTrendChart.vue', [
    'v2-workbench-trend-chart__area', 'v2-workbench-trend-chart__point',
    'v2-workbench-trend-chart__y-label', 'stroke-dasharray',
    'const maximum = computed', 'maximum.value', 'const yAxisLabels = computed',
  ]],
]

const failures = []
for (const [file, needles] of checks) {
  const source = read(file)
  for (const needle of needles) if (!source.includes(needle)) failures.push(`${file} missing ${needle}`)
}
const dashboard = read('src/views/DashboardView.vue')
if (dashboard.includes('>＋ 新建任务<')) failures.push('Dashboard primary action changed from execution reports to task creation')
if (dashboard.includes("title: '系统运行正常'")) failures.push('Dashboard status meaning changed from execution quality to generic system health')
if (dashboard.includes('const passRate') || dashboard.includes('const failRate')) failures.push('Dashboard trend meaning changed from execution counts to percentages')
const shell = read('src/components/AppShell.vue')
if (shell.includes('暂无新通知')) failures.push('Shell gained a notification action that did not exist before the style redesign')
if (shell.includes('v2-shell__search') || shell.includes('showSearchPlaceholder')) failures.push('Shell still contains the removed global search placeholder')
if (shell.includes('showAiConfigPlaceholder') || shell.includes('AI 配置功能将在后续 Phase 迁移')) failures.push('Global AI config is still wired to a placeholder')
const aiConfigDialog = read('src/components/AiConfigDialog.vue')
for (const endpoint of ['/api/ai-config', '/api/ai-config/test']) {
  if (!aiConfigDialog.includes(endpoint)) failures.push(`AI config dialog missing original endpoint ${endpoint}`)
}
const trendChart = read('src/components/v2/workbench/WorkbenchTrendChart.vue')
if (trendChart.includes("const yAxisLabels = ['100', '75', '50', '25', '0']")) {
  failures.push('Trend chart axis was changed from real count scaling to a fixed percentage scale')
}
if (failures.length) {
  console.error('V3 approved baseline fidelity validation failed:')
  failures.forEach((failure) => console.error(`- ${failure}`))
  process.exit(1)
}
console.log('V3 approved baseline fidelity validation passed')
