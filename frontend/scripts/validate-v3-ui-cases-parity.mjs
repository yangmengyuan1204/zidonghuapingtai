import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const view = readFileSync(join(frontendDir, 'src', 'views', 'UiCasesView.vue'), 'utf8')
const apiModule = readFileSync(join(frontendDir, 'src', 'api', 'modules', 'uiCases.js'), 'utf8')
const recordingPanel = readFileSync(join(frontendDir, 'src', 'components', 'ui-cases', 'UiRecordingPanel.vue'), 'utf8')
const preflightPanelPath = join(frontendDir, 'src', 'components', 'ui-cases', 'UiRecordingPreflightPanel.vue')
const preflightPanelSource = existsSync(preflightPanelPath) ? readFileSync(preflightPanelPath, 'utf8') : ''
const failures = []
const requirePattern = (pattern, message) => { if (!pattern.test(view)) failures.push(message) }

for (const file of ['UiCaseForm.vue', 'UiExecutionPanel.vue', 'UiRecordingPanel.vue', 'UiRecordingPreflightPanel.vue']) {
  if (!existsSync(join(frontendDir, 'src', 'components', 'ui-cases', file))) failures.push(`missing ${file}`)
  requirePattern(new RegExp(file.replace('.vue', '')), `UiCasesView does not use ${file}`)
}
for (const contract of [
  'visual-execute',
  'pollVisualExecution',
  'cancelRecordSession',
  'pollRecordSession',
  'submitRecordSave',
  'onBeforeUnmount',
  'stopPolling',
  'stopRecordPolling',
]) requirePattern(new RegExp(contract), `UiCasesView lost ${contract}`)
for (const contract of ['startRecordPreflight', 'pollRecordPreflight', 'saveRecordDraft', 'preflight_run_id']) {
  requirePattern(new RegExp(contract), `UiCasesView missing preflight contract ${contract}`)
}
const preflightStartIndex = view.indexOf('async function startRecordPreflight()')
const preflightPollIndex = view.indexOf('async function pollRecordPreflight(', preflightStartIndex)
const preflightStartBlock = view.slice(preflightStartIndex, preflightPollIndex)
const releaseIndex = preflightStartBlock.indexOf('recordSaving.value = false')
const immediatePollIndex = preflightStartBlock.indexOf('await pollRecordPreflight(generation)')
const intervalPollIndex = preflightStartBlock.indexOf('recordPreflightPollTimer = window.setInterval(() => pollRecordPreflight(generation), 1000)')
if (!(releaseIndex >= 0 && releaseIndex < immediatePollIndex && immediatePollIndex < intervalPollIndex)) {
  failures.push('UiCasesView must finish immediate preflight polling before starting interval polling')
}
for (const contract of ['recordPreflightGeneration', 'recordPreflightPollInFlight', 'generation !== recordPreflightGeneration', 'result.run_id !== recordPreflight.value?.run_id']) {
  requirePattern(new RegExp(contract.replace(/[?.]/g, '\\$&')), `UiCasesView missing stale preflight polling guard ${contract}`)
}
for (const contract of ['startUiRecordPreflight', 'getUiRecordPreflight', 'applyUiRecordLocator', 'listUiCaseRevisions', 'rollbackUiCaseRevision']) {
  if (!apiModule.includes(contract)) failures.push(`uiCases API missing ${contract}`)
}
for (const contract of [
  'getUiRecordProjectConfig',
  'saveUiRecordProjectConfig',
  'startUiRecordRepick',
  'restartUiRecordPreflight',
  'verified_rounds',
  'repair_required',
  'round_2_running',
]) {
  if (!apiModule.includes(contract) && !view.includes(contract) && !preflightPanelSource.includes(contract)) {
    failures.push(`missing verified recording contract ${contract}`)
  }
}
if (!existsSync(join(frontendDir, 'src', 'components', 'ui-cases', 'UiRecordingStartDialog.vue'))) {
  failures.push('missing UiRecordingStartDialog.vue')
} else if (!view.includes('UiRecordingStartDialog')) {
  failures.push('UiCasesView does not use UiRecordingStartDialog')
}
if (!preflightPanelSource.includes("emit('repick'") || !preflightPanelSource.includes("emit('restart'")) {
  failures.push('UiRecordingPreflightPanel missing repick/restart actions')
}
if (!recordingPanel.includes('定位质量')) failures.push('UiRecordingPanel missing locator quality column')
if (!recordingPanel.includes('停止并检查')) failures.push('UiRecordingPanel missing preflight action copy')
if (!view.includes("row.status === 'active'")) failures.push('UiCasesView must hide execution action for draft cases')
if (!view.includes("{ value: 'draft', label: '待修复草稿' }")) failures.push('UiCasesView missing repair-draft status option')
if (existsSync(preflightPanelPath)) {
  if (!preflightPanelSource.includes("emit('adopt'")) failures.push('UiRecordingPreflightPanel missing candidate adopt action')
  if (!preflightPanelSource.includes('item.reasons')) failures.push('UiRecordingPreflightPanel missing locator score reasons')
}
requirePattern(/WorkbenchPageHeader/, 'UiCasesView missing WorkbenchPageHeader')
requirePattern(/WorkbenchPanel/, 'UiCasesView missing WorkbenchPanel')
requirePattern(/--v2-/, 'UiCasesView does not consume V2 tokens')
if (/style="[^\"]*(?:#[0-9a-f]{3,8}|--line|--radius)/i.test(view)) failures.push('UiCasesView retains a raw legacy inline style')

if (failures.length) {
  console.error(`V3 UI cases parity validation failed (${failures.length})`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V3 UI cases parity validation passed')
