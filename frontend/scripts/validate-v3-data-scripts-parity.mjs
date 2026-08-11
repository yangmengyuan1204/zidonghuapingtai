import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8')
const checks = [
  ['src/views/DataScriptsView.vue', ['DataScriptCatalog', 'DataScriptRunner', 'DataAgentWorkspace', 'factoryProjectId', 'factoryEnvId', 'dataScriptTab']],
  ['src/api/modules/dataScripts.js', ['/api/requirement-verifications/data-script-catalog', '/api/data-scripts/', '/api/data-scripts/agent/sessions']],
]

for (const [file, needles] of checks) {
  const source = read(file)
  for (const needle of needles) if (!source.includes(needle)) throw new Error(`${file} missing ${needle}`)
}
console.log('V3 data scripts parity validation passed')
