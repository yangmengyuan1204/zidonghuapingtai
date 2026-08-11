import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const view = fs.readFileSync(path.join(root, 'src/views/RequirementVerificationView.vue'), 'utf8')
const api = fs.readFileSync(path.join(root, 'src/api/modules/requirementVerification.js'), 'utf8')
for (const needle of ['WorkbenchPageHeader', 'preflightTask', 'runTask', 'pauseActiveRun', 'resumeActiveRun', 'cancelActiveRun', 'onBeforeUnmount(stopRunPolling)']) {
  if (!view.includes(needle)) throw new Error(`RequirementVerificationView missing ${needle}`)
}
for (const needle of ['/api/requirement-verifications', '/preflight', '/runs', '/pause', '/resume', '/cancel']) {
  if (!api.includes(needle)) throw new Error(`requirementVerification API missing ${needle}`)
}
console.log('V3 requirement verification parity validation passed')
