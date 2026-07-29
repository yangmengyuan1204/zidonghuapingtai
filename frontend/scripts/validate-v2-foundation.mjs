import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const stylesDir = join(frontendDir, 'src', 'styles', 'v2')
const indexPath = join(stylesDir, 'index.css')

const cssFiles = [
  'tokens.foundation.css',
  'tokens.semantic.css',
  'tokens.component.css',
  'reset.css',
  'base.css',
  'index.css',
]

const requiredTokens = [
  '--v2-color-white',
  '--v2-color-neutral-0',
  '--v2-color-neutral-950',
  '--v2-color-forest-600',
  '--v2-color-red-600',
  '--v2-color-amber-600',
  '--v2-color-blue-600',
  '--v2-color-overlay-transparent',
  '--v2-color-overlay-strong',
  '--v2-font-family-sans',
  '--v2-font-family-mono',
  '--v2-font-size-display',
  '--v2-font-size-heading',
  '--v2-font-size-section',
  '--v2-font-size-body',
  '--v2-font-size-caption',
  '--v2-font-size-tiny',
  '--v2-line-height-tight',
  '--v2-line-height-heading',
  '--v2-line-height-body',
  '--v2-line-height-caption',
  '--v2-font-weight-regular',
  '--v2-font-weight-medium',
  '--v2-font-weight-semibold',
  '--v2-font-weight-bold',
  '--v2-letter-spacing-tight',
  '--v2-letter-spacing-normal',
  '--v2-letter-spacing-wide',
  '--v2-space-micro',
  '--v2-space-1',
  '--v2-space-2',
  '--v2-space-3',
  '--v2-space-4',
  '--v2-space-5',
  '--v2-space-6',
  '--v2-space-7',
  '--v2-radius-xs',
  '--v2-radius-sm',
  '--v2-radius-md',
  '--v2-radius-round',
  '--v2-shadow-dropdown',
  '--v2-shadow-focus',
  '--v2-shadow-selected',
  '--v2-shadow-overlay',
  '--v2-motion-duration',
  '--v2-motion-duration-dialog',
  '--v2-motion-easing',
  '--v2-motion-easing-standard',
  '--v2-motion-reduced',
  '--v2-opacity-pressed',
  '--v2-opacity-disabled',
  '--v2-icon-size-xs',
  '--v2-icon-size-sm',
  '--v2-icon-size-md',
  '--v2-control-height-compact',
  '--v2-control-height-default',
  '--v2-layout-viewport-min',
  '--v2-layout-sidebar-compact',
  '--v2-layout-sidebar',
  '--v2-layout-topbar',
  '--v2-layout-workspace-max',
  '--v2-layout-description-max',
  '--v2-z-base',
  '--v2-z-sticky',
  '--v2-z-sidebar',
  '--v2-z-topbar',
  '--v2-z-dropdown',
  '--v2-z-modal',
  '--v2-z-overlay',
  '--v2-z-toast',
  '--v2-text-primary',
  '--v2-text-secondary',
  '--v2-text-muted',
  '--v2-text-inverse',
  '--v2-text-disabled',
  '--v2-text-danger',
  '--v2-text-success',
  '--v2-surface-canvas',
  '--v2-surface-default',
  '--v2-surface-soft',
  '--v2-surface-hover',
  '--v2-surface-pressed',
  '--v2-surface-disabled',
  '--v2-surface-selected',
  '--v2-surface-overlay',
  '--v2-border-default',
  '--v2-border-strong',
  '--v2-border-focus',
  '--v2-border-danger',
  '--v2-action-primary',
  '--v2-action-primary-hover',
  '--v2-action-primary-pressed',
  '--v2-action-primary-soft',
  '--v2-feedback-success',
  '--v2-feedback-success-soft',
  '--v2-feedback-warning',
  '--v2-feedback-warning-soft',
  '--v2-feedback-danger',
  '--v2-feedback-danger-soft',
  '--v2-feedback-info',
  '--v2-feedback-info-soft',
  '--v2-state-focus-ring',
  '--v2-state-disabled-opacity',
  '--v2-state-selected-shadow',
  '--v2-button-height',
  '--v2-button-height-compact',
  '--v2-button-radius',
  '--v2-button-bg',
  '--v2-button-bg-hover',
  '--v2-button-bg-pressed',
  '--v2-button-text',
  '--v2-button-disabled-opacity',
  '--v2-icon-button-size',
  '--v2-icon-button-size-compact',
  '--v2-icon-button-radius',
  '--v2-icon-button-text',
  '--v2-icon-button-surface-hover',
  '--v2-input-height',
  '--v2-input-height-compact',
  '--v2-input-radius',
  '--v2-input-surface',
  '--v2-input-text',
  '--v2-input-placeholder',
  '--v2-input-border',
  '--v2-input-border-focus',
  '--v2-checkbox-size',
  '--v2-checkbox-radius',
  '--v2-checkbox-border',
  '--v2-checkbox-selected-surface',
  '--v2-checkbox-selected-text',
  '--v2-sidebar-width',
  '--v2-sidebar-width-compact',
  '--v2-sidebar-surface',
  '--v2-sidebar-border',
  '--v2-sidebar-text',
  '--v2-sidebar-text-active',
  '--v2-sidebar-item-hover',
  '--v2-topbar-height',
  '--v2-topbar-surface',
  '--v2-topbar-border',
  '--v2-topbar-text',
  '--v2-card-surface',
  '--v2-card-border',
  '--v2-card-radius',
  '--v2-card-selected-shadow',
  '--v2-table-header-height',
  '--v2-table-row-height',
  '--v2-table-header-surface',
  '--v2-table-row-hover',
  '--v2-table-border',
  '--v2-table-text',
  '--v2-table-text-muted',
  '--v2-dropdown-width',
  '--v2-dropdown-offset',
  '--v2-dropdown-surface',
  '--v2-dropdown-border',
  '--v2-dropdown-radius',
  '--v2-dropdown-shadow',
  '--v2-dropdown-z-index',
  '--v2-pagination-height',
  '--v2-pagination-control-size',
  '--v2-pagination-radius',
  '--v2-pagination-surface',
  '--v2-pagination-surface-active',
  '--v2-pagination-text',
  '--v2-pagination-text-active',
  '--v2-badge-radius',
  '--v2-badge-font-size',
  '--v2-badge-surface',
  '--v2-badge-text',
  '--v2-chip-height',
  '--v2-chip-radius',
  '--v2-chip-surface',
  '--v2-chip-surface-selected',
  '--v2-chip-text',
  '--v2-chip-text-selected',
  '--v2-chip-border',
  '--v2-modal-surface',
  '--v2-modal-overlay',
  '--v2-modal-border',
  '--v2-modal-radius',
  '--v2-modal-shadow',
  '--v2-modal-z-index',
  '--v2-modal-overlay-z-index',
  '--v2-toast-surface',
  '--v2-toast-text',
  '--v2-toast-radius',
  '--v2-toast-shadow',
  '--v2-toast-z-index',
]

const failures = []

function fail(message) {
  failures.push(message)
}

function read(path) {
  return readFileSync(path, 'utf8')
}

function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

function splitSelectors(prelude) {
  const selectors = []
  let start = 0
  let depth = 0
  for (let index = 0; index < prelude.length; index += 1) {
    const char = prelude[index]
    if (char === '(' || char === '[') depth += 1
    if (char === ')' || char === ']') depth -= 1
    if (char === ',' && depth === 0) {
      selectors.push(prelude.slice(start, index).trim())
      start = index + 1
    }
  }
  selectors.push(prelude.slice(start).trim())
  return selectors.filter(Boolean)
}

function findClosingBrace(css, openingIndex) {
  let depth = 0
  for (let index = openingIndex; index < css.length; index += 1) {
    if (css[index] === '{') depth += 1
    if (css[index] === '}') depth -= 1
    if (depth === 0) return index
  }
  return -1
}

function validateScopedRules(css, label) {
  let cursor = 0
  while (cursor < css.length) {
    const openingIndex = css.indexOf('{', cursor)
    if (openingIndex === -1) return
    const closingIndex = findClosingBrace(css, openingIndex)
    if (closingIndex === -1) {
      fail(`${label} contains an unclosed CSS block`)
      return
    }

    const rawPrelude = css.slice(cursor, openingIndex).trim()
    const prelude = rawPrelude.slice(rawPrelude.lastIndexOf(';') + 1).trim()
    const body = css.slice(openingIndex + 1, closingIndex)
    if (prelude.startsWith('@')) {
      validateScopedRules(body, label)
    } else {
      for (const selector of splitSelectors(prelude)) {
        if (!/^\.frontend-v2(?:-portal)?(?=$|[\s.:#[>+~])/.test(selector)) {
          fail(`${label} contains unscoped selector ${selector}`)
        }
      }
    }
    cursor = closingIndex + 1
  }
}

function tokenDeclarations(css) {
  return new Map(
    [...css.matchAll(/(--v2-[a-z0-9-]+)\s*:\s*([^;]+);/gi)]
      .map(([, name, value]) => [name, value.trim()]),
  )
}

function tokenReferences(value) {
  return [...value.matchAll(/var\(\s*(--v2-[a-z0-9-]+)/gi)].map(([, name]) => name)
}

function expectedTokenOwner(name) {
  if (
    /^(?:--v2-text-|--v2-surface-|--v2-action-|--v2-feedback-|--v2-state-)/.test(name)
    || (/^--v2-border-/.test(name) && name !== '--v2-border-width')
  ) {
    return 'tokens.semantic.css'
  }
  if (
    /^(?:--v2-color-|--v2-font-|--v2-line-height-|--v2-letter-spacing-|--v2-space-|--v2-radius-|--v2-shadow-|--v2-motion-|--v2-opacity-|--v2-icon-size-|--v2-control-height-|--v2-size-|--v2-layout-|--v2-z-)/.test(name)
    || name === '--v2-border-width'
  ) {
    return 'tokens.foundation.css'
  }
  return 'tokens.component.css'
}

function walkFiles(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walkFiles(path) : [path]
  })
}

for (const file of cssFiles) {
  const path = join(stylesDir, file)
  if (!existsSync(path)) {
    fail(`missing ${relative(repoDir, path)}`)
  }
}

const existingCss = cssFiles
  .map((file) => join(stylesDir, file))
  .filter(existsSync)
  .map((path) => ({ path, content: read(path) }))

for (const { path, content } of existingCss) {
  const css = stripComments(content)
  const label = relative(repoDir, path)

  if (path !== indexPath && /@layer\b/.test(css)) {
    fail(`${label} declares a layer even though index.css assigns its import layer`)
  }

  if (/:root\b/.test(css)) {
    fail(`${label} contains shared :root`)
  }

  const declarations = [...css.matchAll(/(--[a-z0-9-]+)\s*:/gi)]
  for (const match of declarations) {
    if (!match[1].startsWith('--v2-')) {
      fail(`${label} contains non-V2 token declaration ${match[1]}`)
    }
  }

  if (path !== indexPath) {
    validateScopedRules(css, label)
  }
}

const tokenCss = existingCss
  .filter(({ path }) => path.includes('tokens.'))
  .map(({ content }) => stripComments(content))
  .join('\n')

for (const token of requiredTokens) {
  if (!new RegExp(`${token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*:`).test(tokenCss)) {
    fail(`missing required token ${token}`)
  }
}

const tokenLayers = [
  ['tokens.foundation.css', new Set()],
  ['tokens.semantic.css', new Set(['tokens.foundation.css'])],
  ['tokens.component.css', new Set(['tokens.foundation.css', 'tokens.semantic.css'])],
]
const declarationsByFile = new Map()

for (const [file] of tokenLayers) {
  const path = join(stylesDir, file)
  declarationsByFile.set(file, existsSync(path) ? tokenDeclarations(stripComments(read(path))) : new Map())
}

const tokenOwner = new Map()
for (const [file, declarations] of declarationsByFile) {
  for (const name of declarations.keys()) {
    if (tokenOwner.has(name)) {
      fail(`${name} is declared in both ${tokenOwner.get(name)} and ${file}`)
    }
    tokenOwner.set(name, file)
  }
}

for (const [token, actualOwner] of tokenOwner) {
  const expectedOwner = expectedTokenOwner(token)
  if (actualOwner !== expectedOwner) {
    fail(`${token} must be declared in ${expectedOwner}, not ${actualOwner}`)
  }
}

for (const [file, allowedDependencies] of tokenLayers) {
  const declarations = declarationsByFile.get(file)
  for (const [name, value] of declarations) {
    const references = tokenReferences(value)
    if (file !== 'tokens.foundation.css' && references.length === 0) {
      fail(`${file} token ${name} must reference a lower-level V2 token`)
    }
    if (file !== 'tokens.foundation.css' && /(?:#[0-9a-f]{3,8}|rgba?\(|hsla?\()/i.test(value)) {
      fail(`${file} token ${name} contains a raw color`)
    }
    for (const reference of references) {
      const owner = tokenOwner.get(reference)
      if (!owner) {
        fail(`${file} token ${name} references undefined token ${reference}`)
      } else if (!allowedDependencies.has(owner)) {
        fail(`${file} token ${name} cannot reference ${reference} from ${owner}`)
      }
    }
  }
}

for (const { path, content } of existingCss) {
  for (const reference of tokenReferences(stripComments(content))) {
    if (!tokenOwner.has(reference)) {
      fail(`${relative(repoDir, path)} references undefined token ${reference}`)
    }
  }
}

if (existsSync(indexPath)) {
  const indexCss = stripComments(read(indexPath))
  const expectedLayerOrder = '@layer v2-reset, v2-tokens, v2-base, v2-components, v2-utilities, v2-overrides;'
  const imports = [
    ['tokens.foundation.css', 'v2-tokens'],
    ['tokens.semantic.css', 'v2-tokens'],
    ['tokens.component.css', 'v2-tokens'],
    ['reset.css', 'v2-reset'],
    ['base.css', 'v2-base'],
  ]
  if (!indexCss.includes(expectedLayerOrder)) {
    fail('index.css does not declare the approved V2 layer order')
  }
  if (/@layer[^;{]*\{/.test(indexCss)) {
    fail('index.css must not contain nested layer blocks')
  }
  const expectedImports = imports.map(([file, layer]) => `@import url("./${file}") layer(${layer});`)
  const actualImports = indexCss.match(/@import\b[^;]+;/g) ?? []
  const layerStatements = indexCss.match(/@layer\b[^;{]+;/g) ?? []
  if (actualImports.length !== expectedImports.length) {
    fail(`index.css must contain exactly ${imports.length} layered imports`)
  }
  if (layerStatements.length !== 1 || layerStatements[0] !== expectedLayerOrder) {
    fail('index.css must contain exactly one approved layer-order statement')
  }
  let previous = -1
  for (const [file, layer] of imports) {
    const statement = `@import url("./${file}") layer(${layer});`
    const position = indexCss.indexOf(statement)
    if (position === -1) {
      fail(`index.css does not import ${file} into ${layer}`)
    } else if (position <= previous) {
      fail(`index.css imports ${file} out of order`)
    }
    previous = position
  }
  const unexpectedContent = [expectedLayerOrder, ...expectedImports]
    .reduce((content, statement) => content.replace(statement, ''), indexCss)
    .trim()
  if (unexpectedContent) {
    fail('index.css contains statements outside the approved layer order and imports')
  }
}

const mainPath = join(frontendDir, 'src', 'main.js')
const mainSource = read(mainPath)
const legacyStyleImport = mainSource.indexOf("import './styles/main.css'")
const v2StyleImport = mainSource.indexOf("import './styles/v2/index.css'")
if (v2StyleImport === -1) {
  fail('frontend/src/main.js does not import V2 foundation CSS')
} else if (legacyStyleImport === -1 || v2StyleImport <= legacyStyleImport) {
  fail('V2 foundation CSS must load after existing main.css')
}

const vueIndexPath = join(frontendDir, 'index.html')
const vueIndex = read(vueIndexPath)
const appTag = vueIndex.match(/<div\b(?=[^>]*\s+id=["']app["'])[^>]*>/i)?.[0]
const appClasses = appTag?.match(/(?:^|\s)class=["']([^"']*)["']/i)?.[1].split(/\s+/) ?? []
if (!appTag || !appClasses.includes('frontend-v2')) {
  fail('frontend/index.html #app does not provide the frontend-v2 namespace')
}

const staticDir = join(repoDir, 'static')
const legacyLoaderPattern = /(?:frontend-v2|frontend\/src\/styles\/v2|src\/styles\/v2|styles\/v2\/index\.css|\/v3\/(?:assets\/)?[^"'`]+\.css)/i
for (const path of walkFiles(staticDir).filter((file) => /\.(?:css|html|js)$/i.test(file))) {
  if (legacyLoaderPattern.test(read(path))) {
    fail(`${relative(repoDir, path)} loads or references Vue-only V2 foundation CSS`)
  }
}

if (failures.length) {
  console.error('V2 foundation validation failed:')
  for (const failure of failures) {
    console.error(`- ${failure}`)
  }
  process.exit(1)
}

console.log(`V2 foundation validation passed (${cssFiles.length} CSS files, ${requiredTokens.length} required tokens).`)
