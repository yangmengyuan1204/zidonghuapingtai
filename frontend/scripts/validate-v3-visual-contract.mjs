import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(scriptDir, '..', '..')
const historicalReferences = new Map([
  ['docs/frontend-v2/visual-baseline/VISUAL-CONTRACT.md', '894aa143521a1c8b9b9155629fcdcbb2a59c25a35364ab5e37ddc1bf4b74fd03'],
  ['docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png', '369c441945cee1afa3e3295a01951ec2e281369825668bdbacf3b8e2e1472263'],
])

const issues = []
for (const [path, expectedHash] of historicalReferences) {
  const absolute = resolve(repoRoot, path)
  if (!existsSync(absolute)) {
    issues.push(`${path}: historical visual reference is missing`)
    continue
  }
  const actualHash = createHash('sha256').update(readFileSync(absolute)).digest('hex')
  if (actualHash !== expectedHash) issues.push(`${path}: historical visual reference changed`)
}

if (issues.length) {
  console.error('V3 historical visual contract preservation failed:')
  for (const issue of issues) console.error(`- ${issue}`)
  process.exit(1)
}

const activeContract = spawnSync(process.execPath, [resolve(scriptDir, 'validate-v3-light-visual-contract.mjs')], {
  cwd: repoRoot,
  stdio: 'inherit',
})
if (activeContract.status !== 0) process.exit(activeContract.status || 1)

console.log(`V3 visual contract validation passed (${historicalReferences.size} historical references preserved; light contract active).`)
