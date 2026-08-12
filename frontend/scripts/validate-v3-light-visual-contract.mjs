import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const sha256 = (path) => createHash('sha256').update(readFileSync(resolve(repoRoot, path))).digest('hex')

const references = new Map([
  ['docs/ui-redesign/README-CODEX.md', 'b730290a068f8db408fb235201a5b81db8b1254d319b61f65929e0c8179cf3fe'],
  ['docs/ui-redesign/01-dashboard.png', '20d9b7fa26414accb62ebf99e3f9fc95f5cba9b13abf3abe3a4de56232730613'],
  ['docs/ui-redesign/02-projects.png', '7623c651cb6c50bb4f5a3e0d3c16ab32dfa7ece5604c1f3ddddf4cf1282f468d'],
  ['docs/ui-redesign/03-api-cases.png', '18e2c6ecf4b1a70f9507ab5b9dbe3ab23b268424d9fb58bc2a3b602e4ef19b60'],
  ['docs/ui-redesign/04-data-factory.png', '9d6011275f7836c7bba4aa9713fb5aa7f02dba9cf7bbff8aca65ebf96c49d410'],
  ['docs/ui-redesign/05-requirement-verification.png', '4fc6f7132412b4387b213d2c4e7cd37687b16c7fc7d91d40534feaf75f6a97b8'],
  ['docs/ui-redesign/06-ui-automation.png', '4b22908b924e9cf98be20b0c55ba7935031da081065fa9634a7dcd8508ecd5a1'],
  ['docs/ui-redesign/07-records.png', '77601b0bf4cffec1d748ea106af9ccab6b8c68179caef30c22b061553c307d0f'],
  ['docs/ui-redesign/08-system-regression.png', '9de7600cd6a04103064a065ef7536ca03ae512650b007d79fe5f8da20c756bd1'],
  ['docs/ui-redesign/09-users-ai.png', 'eafe8ff34a9fe362263b44b582a73bf130035af35d9cee08cb82cee2f1d35fbc'],
  ['docs/ui-redesign/10-admin-utilities.png', '931199bbe79ac14d316118ac9bc7a4db1e172b74e90c04c3db3a86c3364f805b'],
  ['docs/ui-redesign/11-login.png', 'f58673304cd0c5d6b15d582b448e3ec0e1b379125106821a24cd8eaf05af7544'],
])

const requiredDeclarations = new Map([
  ['frontend/src/styles/v2/tokens.foundation.css', [
    '--v2-color-brand-blue: #5d87ff;',
    '--v2-color-canvas-neutral: #f4f6f8;',
    '--v2-layout-sidebar: 240px;',
    '--v2-layout-topbar: 60px;',
    '--v2-radius-panel: 10px;',
  ]],
  ['frontend/src/styles/v2/tokens.semantic.css', [
    '--v2-surface-workspace-a3: var(--v2-color-canvas-workspace);',
    '--v2-surface-sidebar-a3: var(--v2-color-sidebar-dark);',
    '--v2-action-primary-a3: var(--v2-color-brand-blue);',
  ]],
  ['frontend/src/styles/v2/tokens.component.css', [
    '--v2-shell-sidebar-width: var(--v2-layout-sidebar);',
    '--v2-shell-sidebar-surface: var(--v2-surface-sidebar-a3);',
    '--v2-shell-workspace-surface: var(--v2-surface-workspace-a3);',
    '--v2-shell-topbar-height: var(--v2-layout-topbar);',
  ]],
  ['static/design-tokens.css', [
    '--color-brand-primary: #5d87ff;',
    '--color-bg-canvas: #f4f6f8;',
    '--color-sidebar: #111827;',
    '--layout-sidebar-width: 240px;',
    '--layout-topbar-height: 60px;',
  ]],
])

const requiredSurfaceSignatures = new Map([
  ['frontend/src/views/DashboardView.vue', '.v2-dashboard :deep(.v2-workbench-panel)'],
  ['frontend/src/views/ProjectsView.vue', '.v2-projects :deep(.v2-workbench-panel__header)'],
  ['frontend/src/views/ApiCasesView.vue', '.v2-api-cases :deep(.v2-base-table)'],
  ['static/styles.css', 'html.v3-embed .factory-grid'],
  ['frontend/src/views/RequirementVerificationView.vue', '.v2-requirement :deep(.v2-workbench-panel)'],
  ['frontend/src/views/UiCasesView.vue', '.v2-ui-cases :deep(.v2-workbench-panel)'],
  ['frontend/src/views/RecordsView.vue', '.v2-records :deep(.v2-workbench-panel)'],
  ['static/system-regression.css', 'html.v3-embed .system-regression-page'],
  ['frontend/src/views/UsersView.vue', '.v2-users :deep(.v2-workbench-panel)'],
  ['frontend/src/components/AiConfigDialog.vue', '.ai-config-dialog__form :deep(.v2-base-input)'],
  ['static/admin/templates.html', '/* v3-enterprise-admin-utilities */'],
  ['static/admin/heal-logs.html', '/* v3-enterprise-admin-utilities */'],
  ['static/login.css', '/* v3-enterprise-login */'],
])

const issues = []
for (const [path, expected] of references) {
  const absolute = resolve(repoRoot, path)
  if (!existsSync(absolute)) issues.push(`${path}: reference missing`)
  else if (sha256(path) !== expected) issues.push(`${path}: reference hash changed`)
}

for (const [path, declarations] of requiredDeclarations) {
  const absolute = resolve(repoRoot, path)
  if (!existsSync(absolute)) {
    issues.push(`${path}: token file missing`)
    continue
  }
  const source = readFileSync(absolute, 'utf8').toLowerCase()
  for (const declaration of declarations) {
    if (!source.includes(declaration.toLowerCase())) issues.push(`${path}: missing ${declaration}`)
  }
}

for (const [path, signature] of requiredSurfaceSignatures) {
  const absolute = resolve(repoRoot, path)
  if (!existsSync(absolute)) {
    issues.push(`${path}: visual surface missing`)
    continue
  }
  if (!readFileSync(absolute, 'utf8').includes(signature)) {
    issues.push(`${path}: missing page-level visual signature ${signature}`)
  }
}

if (issues.length) {
  console.error('V3 enterprise visual contract validation failed:')
  for (const issue of issues) console.error(`- ${issue}`)
  process.exit(1)
}

console.log(`V3 enterprise visual contract validation passed (${references.size} references, ${requiredDeclarations.size} token files, ${requiredSurfaceSignatures.size} visual surfaces).`)
