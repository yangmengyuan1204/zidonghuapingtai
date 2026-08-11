import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const view = fs.readFileSync(path.join(root, 'src/views/SystemRegressionView.vue'), 'utf8')
const api = fs.readFileSync(path.join(root, 'src/api/modules/systemRegression.js'), 'utf8')
for (const needle of ['systemRegressionProjectId', 'systemRegressionEnvId', 'systemRegressionCustomerId', 'case_key', 'reason_code', 'error_message', 'startPolling', 'stopPolling', 'onBeforeUnmount(stopPolling)', 'rerun']) {
  if (!view.includes(needle)) throw new Error(`SystemRegressionView missing ${needle}`)
}
for (const needle of ['/api/system-regression', '/suites/japan/cases', '/cases/', '/batches', '/stop', '/rerun', '/resume-account']) {
  if (!api.includes(needle)) throw new Error(`systemRegression API missing ${needle}`)
}
console.log('V3 system regression parity validation passed')
