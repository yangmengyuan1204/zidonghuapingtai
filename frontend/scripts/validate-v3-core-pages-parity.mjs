import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const read = (path) => readFileSync(join(frontendDir, path), 'utf8')
const failures = []
const pages = [
  ['ProjectsView.vue', ['openProjectForm', 'openEnvForm', 'openTestAccountForm', 'openAccountBinding']],
  ['ApiCasesView.vue', ['openBatchRun', 'onRun', 'onCopy', 'onDelete']],
  ['RecordsView.vue', ['onRerun', 'onShowLog', 'openProtectedFile']],
  ['UsersView.vue', ['openCreate', 'openEdit', 'onDelete']],
]

for (const [file, contracts] of pages) {
  const source = read(`src/views/${file}`)
  if (!/WorkbenchPageHeader/.test(source)) failures.push(`${file} missing WorkbenchPageHeader`)
  if (!/WorkbenchPanel/.test(source)) failures.push(`${file} missing WorkbenchPanel`)
  for (const contract of contracts) {
    if (!new RegExp(`\\b${contract}\\b`).test(source)) failures.push(`${file} lost ${contract}`)
  }
}

const table = read('src/components/AppTable.vue')
if (!/--v2-/.test(table) || /class="(?:table-wrap|panel|empty)"/.test(table)) failures.push('AppTable is not token-native')
const pagination = read('src/components/AppPagination.vue')
if (!/BasePagination/.test(pagination)) failures.push('AppPagination does not delegate to BasePagination')
const form = read('src/components/AppFormDialog.vue')
for (const component of ['BaseModal', 'BaseInput', 'BaseSelect', 'BaseTextarea']) {
  if (!new RegExp(component).test(form)) failures.push(`AppFormDialog missing ${component}`)
}
if (/import\s+AppModal/.test(form)) failures.push('AppFormDialog still depends on legacy AppModal')

if (failures.length) {
  console.error(`V3 core pages parity validation failed (${failures.length})`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V3 core pages parity validation passed')
