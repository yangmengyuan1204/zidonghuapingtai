import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const router = fs.readFileSync(path.join(root, 'src/router/index.js'), 'utf8')
const migration = JSON.parse(fs.readFileSync(path.resolve(root, '../static/migration-config.json'), 'utf8'))
const routeBlock = router.match(/path: '\/requirementVerification'[\s\S]*?meta:/)?.[0] || ''
if (!routeBlock.includes('LegacyEmbedView')) throw new Error('requirement verification must use the complete legacy workflow')
if (routeBlock.includes('RequirementVerificationView')) throw new Error('requirement verification must not use the native catalog view')
if (!migration.migrated.includes('requirementVerification')) throw new Error('requirement verification must stay on the V3 address via migration config')
console.log('V3 requirement verification V3-embed validation passed')
