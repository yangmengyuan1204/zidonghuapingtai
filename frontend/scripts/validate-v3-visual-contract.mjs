import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, extname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(scriptDir, '..', '..')
const baselineImage = 'docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png'
const baselineHash = '369c441945cee1afa3e3295a01951ec2e281369825668bdbacf3b8e2e1472263'

const requiredDeclarations = new Map([
  ['frontend/src/styles/v2/tokens.foundation.css', [
    '--v2-color-navy-950: #132238;',
    '--v2-color-navy-800: #223b5b;',
    '--v2-color-blue-700: #2457ad;',
    '--v2-color-blue-500: #5b8ff0;',
    '--v2-color-canvas-cool: #f5f8fc;',
    '--v2-color-canvas-mist: #e8eef5;',
    '--v2-color-sidebar-slate: #c9d9e7;',
    '--v2-color-section-cool: #dde7f0;',
    '--v2-color-utility-cool: #e7eef4;',
    '--v2-color-context-blue: #d5e3ef;',
    '--v2-color-border-cool: #d1dce6;',
    '--v2-color-border-slate: #b9c8d6;',
    '--v2-color-ink-950: #172b3f;',
    '--v2-layout-sidebar: 220px;',
    '--v2-layout-topbar: 56px;',
    '--v2-layout-workspace-max: none;',
    '--v2-radius-panel: 8px;',
    '--v2-shadow-panel: 0 1px 2px rgba(25, 48, 78, 0.025);',
  ]],
  ['frontend/src/styles/v2/tokens.semantic.css', [
    '--v2-surface-workspace: var(--v2-color-canvas-cool);',
    '--v2-surface-sidebar: var(--v2-color-navy-950);',
    '--v2-action-primary: var(--v2-color-blue-700);',
    '--v2-border-panel: var(--v2-color-border-slate);',
  ]],
  ['frontend/src/styles/v2/tokens.component.css', [
    '--v2-shell-sidebar-width: var(--v2-layout-sidebar);',
    '--v2-shell-topbar-height: var(--v2-layout-topbar);',
    '--v2-panel-radius: var(--v2-radius-panel);',
    '--v2-panel-shadow: var(--v2-shadow-panel);',
  ]],
])

const lockedColors = [
  '#132238', '#223b5b', '#2457ad', '#5b8ff0', '#f5f8fc',
  '#e8eef5', '#c9d9e7', '#dde7f0', '#e7eef4', '#d5e3ef',
  '#d1dce6', '#b9c8d6', '#172b3f',
]
const gradientPattern = /(?:linear|radial|conic)-gradient\s*\(/i
const backdropPattern = /(?:-webkit-)?backdrop-filter\s*:/i

function walkFiles(root, acceptedExtensions) {
  if (!existsSync(root)) return []
  const results = []
  for (const entry of readdirSync(root)) {
    const absolute = resolve(root, entry)
    if (statSync(absolute).isDirectory()) results.push(...walkFiles(absolute, acceptedExtensions))
    else if (acceptedExtensions.has(extname(entry))) results.push(absolute)
  }
  return results
}

function normalizedPath(absolutePath) {
  return relative(repoRoot, absolutePath).replaceAll('\\', '/')
}

function validateSource(path, source) {
  const issues = []

  if (gradientPattern.test(source) && !path.endsWith('/BaseSkeleton.vue')) {
    issues.push(`${path}: decorative gradient is prohibited`)
  }
  if (backdropPattern.test(source)) {
    issues.push(`${path}: backdrop-filter is prohibited`)
  }

  if (!path.endsWith('/tokens.foundation.css')) {
    for (const color of lockedColors) {
      if (source.toLowerCase().includes(color)) issues.push(`${path}: locked palette color ${color} must come from a V2 token`)
    }
  }

  if (path.endsWith('/tokens.component.css')) {
    for (const match of source.matchAll(/(^|[;{]\s*)(--[\w-]+)\s*:/gm)) {
      if (!match[2].startsWith('--v2-')) issues.push(`${path}: component custom property ${match[2]} must use the --v2- prefix`)
    }
  }

  for (const match of source.matchAll(/box-shadow\s*:\s*([^;]+)/gi)) {
    const value = match[1].trim()
    if (value === 'none' || value.includes('var(')) continue
    const lengths = value.match(/^(?:inset\s+)?(-?\d*\.?\d+)(?:px)?\s+(-?\d*\.?\d+)(?:px)?\s+(-?\d*\.?\d+)(?:px)?/i)
    const blur = Math.abs(Number(lengths?.[3] || 0))
    if (blur > 24) issues.push(`${path}: raw shadow blur ${blur}px exceeds the overlay ceiling and must use a V2 shadow token`)
    else if (blur > 8) issues.push(`${path}: raw panel shadow blur ${blur}px exceeds the 8px panel limit`)
  }

  return issues
}

function validateRequiredDeclarations() {
  const issues = []
  for (const [path, declarations] of requiredDeclarations) {
    const absolute = resolve(repoRoot, path)
    if (!existsSync(absolute)) {
      issues.push(`${path}: required token file is missing`)
      continue
    }
    const source = readFileSync(absolute, 'utf8')
    for (const declaration of declarations) {
      if (!source.includes(declaration)) issues.push(`${path}: missing locked declaration ${declaration}`)
    }
  }
  return issues
}

function validateBaselineAsset() {
  const absolute = resolve(repoRoot, baselineImage)
  if (!existsSync(absolute)) return [`${baselineImage}: approved baseline image is missing`]
  const actualHash = createHash('sha256').update(readFileSync(absolute)).digest('hex')
  return actualHash === baselineHash ? [] : [`${baselineImage}: SHA-256 changed from the approved baseline`]
}

function runSelfCheck() {
  const sample = `
    .sample {
      --brand-color: #132238;
      background: linear-gradient(#fff, #000);
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }
  `
  const issues = validateSource('frontend/src/styles/v2/tokens.component.css', sample)
  const expectedFragments = ['decorative gradient', 'backdrop-filter', 'locked palette color', '--v2- prefix', 'shadow blur']
  for (const fragment of expectedFragments) {
    if (!issues.some((issue) => issue.includes(fragment))) {
      throw new Error(`visual contract validator self-check did not detect ${fragment}`)
    }
  }
}

runSelfCheck()

const productionFiles = [
  ...walkFiles(resolve(repoRoot, 'frontend/src/styles/v2'), new Set(['.css'])),
  ...walkFiles(resolve(repoRoot, 'frontend/src/components'), new Set(['.vue'])),
  ...walkFiles(resolve(repoRoot, 'frontend/src/views'), new Set(['.vue'])),
]
const phaseThreeLegacyExemptions = new Set(['frontend/src/components/AppModal.vue'])

const issues = [...validateBaselineAsset(), ...validateRequiredDeclarations()]
for (const absolute of productionFiles) {
  const path = normalizedPath(absolute)
  if (phaseThreeLegacyExemptions.has(path)) continue
  issues.push(...validateSource(path, readFileSync(absolute, 'utf8')))
}

if (issues.length) {
  console.error('V3 visual contract validation failed:')
  for (const issue of issues) console.error(`- ${issue}`)
  process.exitCode = 1
} else {
  console.log(`V3 visual contract validation passed (${requiredDeclarations.size} token files, ${productionFiles.length} production style sources).`)
}
