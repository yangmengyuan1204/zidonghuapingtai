import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const router = fs.readFileSync(path.join(root, 'src/router/index.js'), 'utf8')
const shell = fs.readFileSync(path.join(root, 'src/components/AppShell.vue'), 'utf8')
const migration = JSON.parse(fs.readFileSync(path.resolve(root, '../static/migration-config.json'), 'utf8'))
const dataScriptsBlock = router.match(/path: '\/dataScripts'[\s\S]*?meta:/)?.[0] || ''
if (!dataScriptsBlock.includes('LegacyEmbedView')) throw new Error('dataScripts no longer preserves its original feature page')
if (dataScriptsBlock.includes('DataScriptsView')) throw new Error('dataScripts must not use the native catalog view')
if (!migration.migrated.includes('dataScripts')) throw new Error('dataScripts must stay on the V3 address via migration config')
if (!shell.includes('dataScripts')) throw new Error('AppShell missing dataScripts')
const requirementBlock = router.match(/path: '\/requirementVerification'[\s\S]*?meta:/)?.[0] || ''
if (!requirementBlock.includes('LegacyEmbedView')) throw new Error('requirementVerification no longer preserves its original feature page')
if (requirementBlock.includes('RequirementVerificationView')) throw new Error('requirementVerification must not use the native catalog view')
if (!migration.migrated.includes('requirementVerification')) throw new Error('requirementVerification must stay on the V3 address via migration config')
if (!shell.includes('requirementVerification')) throw new Error('AppShell missing requirementVerification')
const systemRegressionBlock = router.match(/path: '\/systemRegression'[\s\S]*?meta:/)?.[0] || ''
if (!systemRegressionBlock.includes('LegacyEmbedView')) throw new Error('systemRegression no longer preserves its original feature page')
if (systemRegressionBlock.includes('SystemRegressionView')) throw new Error('systemRegression must not use the native catalog view')
if (!migration.migrated.includes('systemRegression')) throw new Error('systemRegression must stay on the V3 address via migration config')
if (!shell.includes('systemRegression')) throw new Error('AppShell missing systemRegression')
if (!/path:\s*'\/:pathMatch\(\.\*\)\*'[\s\S]*?redirect:\s*'\/dashboard'/.test(router)) {
  throw new Error('router missing authenticated catch-all recovery')
}
const navigation = fs.readFileSync(path.join(root, 'src/services/navigation.js'), 'utf8')
const loadIndex = navigation.indexOf('await loadMigrationConfig()')
const migratedIndex = navigation.indexOf('if (isMigrated(resolvedKey)')
const hasRouteIndex = navigation.indexOf('router.hasRoute(resolvedKey)')
if (loadIndex < 0 || migratedIndex < loadIndex || (hasRouteIndex >= 0 && hasRouteIndex < migratedIndex)) {
  throw new Error('Vue navigation does not honor migration config before registered routes')
}
for (const [name, source] of [['router', router], ['AppShell', shell], ['migration config', JSON.stringify(migration)]]) {
  if (/apiHarvester|ApiHarvester/.test(source)) throw new Error(`${name} still exposes retired API harvester`)
}
for (const retiredPath of [
  path.join(root, 'src/views/ApiHarvesterView.vue'),
  path.join(root, 'src/api/modules/apiHarvester.js'),
]) {
  if (fs.existsSync(retiredPath)) throw new Error(`retired API harvester file still exists: ${retiredPath}`)
}
console.log('V3 route migration validation passed')
