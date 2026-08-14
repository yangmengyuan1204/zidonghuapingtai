import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')

const paths = {
  embedView: join(frontendDir, 'src/views/LegacyEmbedView.vue'),
  router: join(frontendDir, 'src/router/index.js'),
  appShell: join(frontendDir, 'src/components/AppShell.vue'),
  migrationConfig: join(repoDir, 'static/migration-config.json'),
  migrationBridge: join(repoDir, 'static/migration-bridge.js'),
}

function read(file) {
  return readFileSync(file, 'utf8')
}

function main() {
  for (const file of Object.values(paths)) {
    if (!existsSync(file)) throw new Error(`Required source is missing: ${file}`)
  }

  const issues = []
  const embed = read(paths.embedView)
  const router = read(paths.router)
  const appShell = read(paths.appShell)
  const bridge = read(paths.migrationBridge)
  const config = JSON.parse(read(paths.migrationConfig))

  if (!/v3_embed=1/.test(embed)) issues.push('LegacyEmbedView must load legacy with ?v3_embed=1')
  if (!/#\/\$\{viewKey/.test(embed) && !/`\/\?v3_embed=1#\/\$\{viewKey\.value\}`/.test(embed)) {
    issues.push('LegacyEmbedView must target /?v3_embed=1#/<viewKey>')
  }
  if (!/\.sidebar/.test(embed) || !/\.topbar/.test(embed)) {
    issues.push('LegacyEmbedView must inject CSS that hides legacy .sidebar and .topbar')
  }

  for (const key of ['dataScripts', 'requirementVerification', 'systemRegression']) {
    if (!new RegExp(`name:\\s*'${key}'`).test(router)) issues.push(`router missing ${key} route name`)
    if (!new RegExp(`viewKey:\\s*'${key}'`).test(router)) issues.push(`router missing ${key} viewKey meta`)
    const routeBlock = router.match(new RegExp(`path:\\s*'\\/${key}'[\\s\\S]*?meta:\\s*\\{\\s*viewKey:\\s*'${key}'`))?.[0] || ''
    if (!/LegacyEmbedView/.test(routeBlock)) issues.push(`${key} must preserve its original legacy feature page`)
  }
  for (const key of ['dataScripts', 'requirementVerification', 'systemRegression']) {
    if (!(config.migrated || []).includes(key)) {
      issues.push(`migration-config must mark ${key} migrated so the V3 shell keeps /v3/${key}`)
    }
  }
  if (!/LegacyEmbedView\.vue/.test(router)) issues.push('router must retain the original feature page bridge')

  for (const key of ['dataScripts', 'requirementVerification', 'systemRegression']) {
    if (!new RegExp(`\\b${key}\\b`).test(appShell)) issues.push(`AppShell missing navigation item ${key}`)
  }
  if (/apiHarvester|ApiHarvester/.test(router) || /apiHarvester|ApiHarvester/.test(appShell)) {
    issues.push('retired API harvester must not remain in Vue navigation')
  }
  if ((config.migrated || []).includes('apiHarvester')) issues.push('migration-config still exposes retired apiHarvester')

  if (!/function isV3Embed\s*\(/.test(bridge)) issues.push('migration-bridge must detect v3_embed mode')
  if (!/migratedSet\.has\(view\)\s*&&\s*!isV3Embed\(\)/.test(bridge)) {
    issues.push('migration-bridge activateInitialHash must skip redirect when embedding')
  }
  if (!/if\s*\(isV3Embed\(\)\)\s*return;/.test(bridge)) {
    issues.push('migration-bridge click interceptor must skip redirect when embedding')
  }

  if (issues.length) throw new Error(issues.join('\n- '))
  console.log('V2 original feature page preservation validation passed.')
}

try {
  main()
} catch (error) {
  console.error(`V2 legacy embed validation failed: ${error.message}`)
  process.exitCode = 1
}
