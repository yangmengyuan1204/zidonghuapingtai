import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const view = readFileSync(join(frontendDir, 'src', 'views', 'UiCasesView.vue'), 'utf8')
const failures = []
const requirePattern = (pattern, message) => { if (!pattern.test(view)) failures.push(message) }

for (const file of ['UiCaseForm.vue', 'UiExecutionPanel.vue', 'UiRecordingPanel.vue']) {
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
