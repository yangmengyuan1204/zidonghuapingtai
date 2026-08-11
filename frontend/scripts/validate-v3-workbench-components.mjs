import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const componentsDir = join(frontendDir, 'src', 'components', 'v2', 'workbench')
const componentNames = [
  'WorkbenchPageHeader',
  'WorkbenchMetricRail',
  'WorkbenchPanel',
  'WorkbenchTrendChart',
  'WorkbenchAttentionList',
  'WorkbenchStatus',
]
const failures = []

function fail(message) {
  failures.push(message)
}

function read(path) {
  return readFileSync(path, 'utf8')
}

const forbiddenDependency = /(?:vue-router|pinia|axios|stores\/|api\/|services\/|localStorage|sessionStorage|\bfetch\s*\(|XMLHttpRequest)/i
const forbiddenRawColor = /(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i
const forbiddenEffect = /(?:linear-gradient|radial-gradient|backdrop-filter|filter\s*:)/i

for (const name of componentNames) {
  const path = join(componentsDir, `${name}.vue`)
  if (!existsSync(path)) {
    fail(`missing ${name}.vue`)
    continue
  }

  const source = read(path)
  if (forbiddenDependency.test(source)) fail(`${name} references business or browser state`)
  if (forbiddenRawColor.test(source)) fail(`${name} contains a raw color`)
  if (forbiddenEffect.test(source)) fail(`${name} contains a prohibited visual effect`)
  if (!/<style\s+scoped>/.test(source)) fail(`${name} must contain one scoped style block`)
  if (!/var\(--v2-/.test(source)) fail(`${name} does not consume V2 tokens`)

  for (const [, value] of source.matchAll(/(?<!:)class=["']([^"']+)["']/g)) {
    for (const className of value.split(/\s+/).filter(Boolean)) {
      if (!className.startsWith('v2-workbench-')) {
        fail(`${name} uses non-workbench class ${className}`)
      }
    }
  }
}

const indexPath = join(componentsDir, 'index.js')
if (!existsSync(indexPath)) {
  fail('missing workbench/index.js')
} else {
  const indexSource = read(indexPath)
  for (const name of componentNames) {
    if (!new RegExp(`export\\s+\\{\\s*default\\s+as\\s+${name}\\s*\\}`).test(indexSource)) {
      fail(`index.js does not export ${name}`)
    }
  }
}

if (existsSync(join(componentsDir, 'WorkbenchTrendChart.vue'))) {
  const chart = read(join(componentsDir, 'WorkbenchTrendChart.vue'))
  for (const prop of ['labels', 'passed', 'failed']) {
    if (!new RegExp(`\\b${prop}\\s*:`).test(chart)) fail(`WorkbenchTrendChart is missing ${prop} prop`)
  }
  if (!/<svg\b/.test(chart) || !/role="img"/.test(chart)) fail('WorkbenchTrendChart must render an accessible SVG')
  if (!/<title>/.test(chart)) fail('WorkbenchTrendChart must provide an SVG title')
  if (!/v2-workbench-trend-chart__empty/.test(chart)) fail('WorkbenchTrendChart must provide an empty state')
}

if (existsSync(join(componentsDir, 'WorkbenchAttentionList.vue'))) {
  const list = read(join(componentsDir, 'WorkbenchAttentionList.vue'))
  if (!/defineEmits\(\[\s*['"]action['"]\s*\]\)/.test(list)) fail('WorkbenchAttentionList must emit action(id)')
  if (!/emit\(['"]action['"],\s*item\.id\)/.test(list)) fail('WorkbenchAttentionList action must carry item.id')
}

if (existsSync(join(componentsDir, 'WorkbenchMetricRail.vue'))) {
  const rail = read(join(componentsDir, 'WorkbenchMetricRail.vue'))
  if (!/\bitems\s*:\s*\{[\s\S]*?type:\s*Array/.test(rail)) fail('WorkbenchMetricRail must accept an items array')
}

if (failures.length) {
  console.error(`V3 workbench component validation failed (${failures.length})`)
  for (const message of failures) console.error(`- ${message}`)
  process.exit(1)
}

console.log(`V3 workbench component validation passed (${componentNames.length} components)`)
