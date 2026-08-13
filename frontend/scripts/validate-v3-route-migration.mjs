import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const router = fs.readFileSync(path.join(root, 'src/router/index.js'), 'utf8')
const shell = fs.readFileSync(path.join(root, 'src/components/AppShell.vue'), 'utf8')
const migration = JSON.parse(fs.readFileSync(path.resolve(root, '../static/migration-config.json'), 'utf8'))
for (const key of ['dataScripts', 'requirementVerification', 'systemRegression']) {
  const block = router.match(new RegExp(`path: '\\/${key}'[\\s\\S]*?meta:`))?.[0] || ''
  if (!block.includes('LegacyEmbedView')) throw new Error(`${key} no longer preserves its original feature page`)
  if (migration.migrated.includes(key)) throw new Error(`migration config incorrectly marks ${key} as native`)
  if (!shell.includes(key)) throw new Error(`AppShell missing ${key}`)
}
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
