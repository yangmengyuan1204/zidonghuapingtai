import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const sourceFaviconPath = join(frontendDir, 'public', 'favicon.ico')
const builtFaviconPath = join(frontendDir, 'dist', 'favicon.ico')
const builtMainHtmlPath = join(frontendDir, 'dist', 'index.html')
const mainHtmlPath = join(frontendDir, 'index.html')
const labHtmlPath = join(frontendDir, 'dev', 'v2-base-components.html')
const viteConfigPath = join(frontendDir, 'vite.config.js')
const appSetupPath = join(repoDir, 'app', 'core', 'app_setup.py')
const componentTokenPath = join(frontendDir, 'src', 'styles', 'v2', 'tokens.component.css')
const foundationTokenPath = join(frontendDir, 'src', 'styles', 'v2', 'tokens.foundation.css')
const failures = []

const approvedVitePluginSource = `const sharedFavicon = readFileSync(new URL('./public/favicon.ico', import.meta.url))

function preserveRootFaviconHref() {
  return {
    name: 'preserve-root-favicon-href',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url !== '/favicon.ico') return next()
        response.statusCode = 200
        response.setHeader('Content-Type', 'image/vnd.microsoft.icon')
        response.setHeader('Content-Length', String(sharedFavicon.length))
        response.end(sharedFavicon)
      })
    },
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const normalizedFavicon = html.replace(/<link\\b[^>]*>/gi, (tag) => {
          const rel = tag.match(/\\brel=(["'])(.*?)\\1/i)?.[2].split(/\\s+/) ?? []
          const href = tag.match(/\\bhref=(["'])(.*?)\\1/i)?.[2]
          if (!rel.includes('icon') || href !== '/v3/favicon.ico') return tag
          return tag.replace(/\\bhref=(["'])\\/v3\\/favicon\\.ico\\1/i, 'href="/favicon.ico"')
        })
        return normalizedFavicon.replace(
          /src=(["'])\\/v3\\/static\\/v2-theme-lock\\.js([^"']*)\\1/i,
          'src="/static/v2-theme-lock.js$2"',
        )
      },
    },
  }
}
`

const protectedFiles = new Map([
  ['frontend/src/views/ApiCasesView.vue', 'eea28f1ec46333f6d98e58d37322aac6f11ea0884f205be16d3e763491d2673e'],
  ['frontend/src/components/AppFormDialog.vue', 'edd453d64fd359e40a7bc050044108f5ac4789f2e42ded006d94d2cbfffedb0d'],
  ['frontend/src/components/v2/base/BaseSelect.vue', '9bf95632c71540f93a7e4d8919237e5a36dcd9e4fabce1b4fa081b62c72b170a'],
  ['frontend/src/components/v2/base/BaseTextarea.vue', 'fcc71eac1c0cafea0066442be0b78333675e0bdcde55be785d9af539c3015c88'],
  ['frontend/src/components/v2/base/BaseTable.vue', 'cae8fb54b01e628926e53c7453ca01a278a9527ccc245f58ae128eee56807b8d'],
  ['frontend/src/router/index.js', '3e4f2b838d35836ea3a0e35ec53676f417d6fa72a9185a75e9d51b538b3edbe8'],
  ['frontend/src/stores/auth.js', '0c1401d4fe0b66e0dce15cb190a1b266b8d6a96ada4191634e6791892e17aa8d'],
  ['frontend/src/stores/app.js', '7ed84fa1928bc86bd17ac001dc63e3f3d623dca7426d103859248c60793ab93b'],
  ['frontend/src/stores/toast.js', '1ae4737ce5d593bc60ba9a3af02e33c1c6cfb0c8c06fa9377a5d66f3f81d5def'],
])

function fail(message) {
  failures.push(message)
}

function digest(value) {
  return createHash('sha256').update(value).digest('hex')
}

function normalizedText(value) {
  return value.replaceAll('\r\n', '\n')
}

export function validateProtectedDigest(actualDigest, expectedDigest, path) {
  return actualDigest === expectedDigest ? [] : [`protected Phase 5.5D file changed: ${path}`]
}

export function validateAssetState({ sourceExists, buildExists }) {
  const issues = []
  if (!sourceExists) issues.push('shared source favicon is missing')
  if (!buildExists) issues.push('built favicon artifact is missing')
  return issues
}

export function validateIcoBuffer(buffer) {
  const issues = []
  if (!Buffer.isBuffer(buffer) || buffer.length < 22) return ['favicon is too small to be a valid ICO']
  const reserved = buffer.readUInt16LE(0)
  const type = buffer.readUInt16LE(2)
  const imageCount = buffer.readUInt16LE(4)
  if (reserved !== 0 || type !== 1) issues.push('favicon has an invalid ICO header')
  if (imageCount < 1 || imageCount > 256) issues.push('favicon has an invalid image count')

  const directoryEnd = 6 + imageCount * 16
  if (directoryEnd > buffer.length) return [...issues, 'favicon directory exceeds file length']
  for (let index = 0; index < imageCount; index += 1) {
    const entryOffset = 6 + index * 16
    const width = buffer[entryOffset] || 256
    const height = buffer[entryOffset + 1] || 256
    const imageSize = buffer.readUInt32LE(entryOffset + 8)
    const imageOffset = buffer.readUInt32LE(entryOffset + 12)
    if (width < 16 || height < 16) issues.push(`favicon image ${index + 1} is not recognisable at favicon size`)
    if (imageSize === 0 || imageOffset < directoryEnd || imageOffset + imageSize > buffer.length) {
      issues.push(`favicon image ${index + 1} has an invalid payload range`)
      continue
    }
    const pngSignature = buffer.subarray(imageOffset, imageOffset + 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
    const dibHeaderSize = imageSize >= 4 ? buffer.readUInt32LE(imageOffset) : 0
    if (!pngSignature && dibHeaderSize < 40) issues.push(`favicon image ${index + 1} is neither PNG-compressed nor a valid DIB`)
  }
  return issues
}

export function validateAssetParity(sourceBuffer, builtBuffer) {
  const issues = []
  if (sourceBuffer.length !== builtBuffer.length) issues.push('built favicon size does not match the shared source asset')
  if (digest(sourceBuffer) !== digest(builtBuffer)) issues.push('built favicon does not match the shared source asset')
  return issues
}

export function validateComponentTokenIsolation(source) {
  const issues = []
  if (/(?:\/favicon\.ico|\/v3\/favicon\.ico|favicon\.(?:ico|png|svg|webp))/i.test(source)) {
    issues.push('component tokens must not contain a favicon resource path')
  }
  if (/--v2-favicon-[a-z0-9-]+\s*:/i.test(source)) issues.push('favicon-specific component tokens are forbidden')
  if (/(?:data:image|https?:\/\/)[^;)}]*(?:favicon|icon)/i.test(source)) {
    issues.push('component tokens must not embed or reference an external favicon')
  }
  return issues
}

export function validateSourceFaviconInventory(publicNames, duplicateAssetPaths = []) {
  const issues = []
  const publicFavicons = publicNames.filter((name) => /^favicon\./i.test(name))
  if (publicFavicons.length !== 1 || publicFavicons[0] !== 'favicon.ico') {
    issues.push('frontend/public must contain only the shared favicon.ico')
  }
  for (const path of duplicateAssetPaths) issues.push(`duplicate favicon asset is forbidden: ${path}`)
  return issues
}

export function validateHtmlReference(source) {
  const issues = []
  const iconLinks = [...source.matchAll(/<link\b[^>]*\brel=["']icon["'][^>]*>/gi)].map(([tag]) => tag)
  if (iconLinks.length !== 1) issues.push('HTML must contain exactly one explicit favicon link')
  const link = iconLinks[0] ?? ''
  if (!/\bhref=["']\/favicon\.ico["']/.test(link)) issues.push('favicon href must be exactly /favicon.ico')
  if (!/\btype=["']image\/vnd\.microsoft\.icon["']/.test(link)) issues.push('favicon MIME type must match the ICO resource')
  if (/\/v3\/favicon\.ico|data:|base64/i.test(source)) issues.push('HTML contains a forbidden favicon path or inline payload')
  return issues
}

export function validateBuiltHtmlReference(source) {
  const issues = validateHtmlReference(source)
  if (!source.includes('href="/favicon.ico"')) issues.push('production HTML must preserve the absolute root favicon href')
  if (!/<script\b[^>]*\bsrc=["']\/v3\/assets\/[^"']+\.js["']/i.test(source)) issues.push('production entry JavaScript must retain the /v3/ base')
  if (!/<link\b[^>]*\brel=["']stylesheet["'][^>]*\bhref=["']\/v3\/assets\/[^"']+\.css["']/i.test(source)) {
    issues.push('production entry CSS must retain the /v3/ base')
  }
  if (/(?:src|href)=["']\/assets\//i.test(source)) issues.push('favicon preservation must not rewrite entry JS/CSS to the root')
  return issues
}

export function validateViteConfig(source) {
  const issues = []
  const normalized = normalizedText(source)
  if (!/^\s*base:\s*["']\/v3\/["'],?\s*$/m.test(normalized)) issues.push('Vite global base must remain /v3/')
  if (!normalized.includes(approvedVitePluginSource)) issues.push('Vite must contain the approved root asset development mapping and HTML transform hook')
  if (!/plugins:\s*\[vue\(\),\s*preserveRootFaviconHref\(\)\]/.test(normalized)) issues.push('favicon preservation plugin must be registered without replacing Vue')
  if (/replace\(\/\\\/v3\\\//.test(normalized) || /renderBuiltUrl/.test(normalized)) issues.push('broad Vite URL rewriting is forbidden')
  return issues
}

export function validateViteDevelopmentMapping(source) {
  const issues = []
  if (!/from ["']node:fs["']/.test(source) || !/readFileSync/.test(source)) issues.push('Vite development favicon mapping must read the shared ICO')
  if (!/new URL\(["']\.\/public\/favicon\.ico["'],\s*import\.meta\.url\)/.test(source)) issues.push('Vite development mapping must target frontend/public/favicon.ico')
  if (!/configureServer\(server\)/.test(source) || !/server\.middlewares\.use/.test(source)) issues.push('Vite development server must register an exact favicon middleware')
  if (!/request\.url\s*!==\s*["']\/favicon\.ico["']/.test(source)) issues.push('Vite development middleware must reject every non-favicon request')
  if (!/setHeader\(["']Content-Type["'],\s*["']image\/vnd\.microsoft\.icon["']\)/.test(source)) issues.push('Vite development favicon Content-Type must match the FastAPI contract')
  if (!/response\.end\(sharedFavicon\)/.test(source)) issues.push('Vite development middleware must return the shared ICO bytes')
  return issues
}

export function validateSetupMapping(source) {
  const issues = []
  if (!/from fastapi\.responses import FileResponse/.test(source)) issues.push('FastAPI setup must import FileResponse')
  if (!/favicon_path\s*=\s*BASE_DIR\s*\/\s*["']frontend["']\s*\/\s*["']public["']\s*\/\s*["']favicon\.ico["']/.test(source)) {
    issues.push('FastAPI favicon mapping must target frontend/public/favicon.ico')
  }
  if (!/@app\.get\(["']\/favicon\.ico["'],\s*include_in_schema=False\)/.test(source)) {
    issues.push('FastAPI must register GET /favicon.ico outside the API schema')
  }
  if (!/return FileResponse\(favicon_path,\s*media_type=["']image\/vnd\.microsoft\.icon["']\)/.test(source)) {
    issues.push('FastAPI favicon route must return the real ICO with the correct Content-Type')
  }
  return issues
}

export function validateSetupRouteOrdering(source) {
  const issues = []
  const faviconIndex = source.indexOf('@app.get("/favicon.ico", include_in_schema=False)')
  const spaFallbackIndex = source.indexOf('@app.get("/v3/{path:path}", include_in_schema=False)')
  if (faviconIndex < 0) issues.push('FastAPI favicon route is missing before SPA fallback evaluation')
  if (spaFallbackIndex >= 0 && faviconIndex > spaFallbackIndex) issues.push('FastAPI favicon route must be registered before the SPA fallback')
  if (/@app\.get\(["']\/{path:path}["']/.test(source.slice(0, Math.max(0, faviconIndex)))) {
    issues.push('a root catch-all route may swallow /favicon.ico')
  }
  return issues
}

function stripApprovedHtmlChange(source) {
  return normalizedText(source).replace(/^\s*<link rel="icon" href="\/favicon\.ico" type="image\/vnd\.microsoft\.icon" \/>\n/m, '')
}

function stripApprovedSetupChange(source) {
  return normalizedText(source)
    .replace('from fastapi.responses import FileResponse\n', '')
    .replace(/\n    favicon_path = BASE_DIR \/ "frontend" \/ "public" \/ "favicon\.ico"\n\n    @app\.get\("\/favicon\.ico", include_in_schema=False\)\n    async def favicon\(\) -> FileResponse:\n        return FileResponse\(favicon_path, media_type="image\/vnd\.microsoft\.icon"\)\n/, '')
}

function stripApprovedViteChange(source) {
  return normalizedText(source)
    .replace("import { readFileSync } from 'node:fs'\n", '')
    .replace(`\n${approvedVitePluginSource}\n`, '\n')
    .replace('plugins: [vue(), preserveRootFaviconHref()],', 'plugins: [vue()],')
}

for (const issue of validateAssetState({
  sourceExists: existsSync(sourceFaviconPath),
  buildExists: existsSync(builtFaviconPath),
})) fail(issue)

if (existsSync(sourceFaviconPath)) {
  for (const issue of validateIcoBuffer(readFileSync(sourceFaviconPath))) fail(issue)
}
if (existsSync(builtFaviconPath)) {
  const builtBuffer = readFileSync(builtFaviconPath)
  for (const issue of validateIcoBuffer(builtBuffer)) fail(`build artifact: ${issue}`)
  if (existsSync(sourceFaviconPath)) {
    for (const issue of validateAssetParity(readFileSync(sourceFaviconPath), builtBuffer)) fail(issue)
  }
}
if (!existsSync(builtMainHtmlPath)) {
  fail('built production HTML is missing')
} else {
  for (const issue of validateBuiltHtmlReference(readFileSync(builtMainHtmlPath, 'utf8'))) {
    fail(`build artifact: ${issue}`)
  }
}

for (const [path, expectedDigest] of protectedFiles) {
  const absolutePath = join(repoDir, path)
  if (!existsSync(absolutePath)) fail(`missing protected Phase 5.5D file ${path}`)
  else for (const issue of validateProtectedDigest(digest(readFileSync(absolutePath)), expectedDigest, path)) fail(issue)
}

if (!existsSync(foundationTokenPath)) fail('missing protected V2 foundation token file')
else if (digest(readFileSync(foundationTokenPath)) !== '1254f501de2c04c6add82208717e393900c65e1bbdb564a4d33af702d6ab770c') {
  fail('V2 foundation token file changed outside an approved foundation phase')
}
if (!existsSync(componentTokenPath)) fail('missing shared V2 component token file')
else for (const issue of validateComponentTokenIsolation(readFileSync(componentTokenPath, 'utf8'))) fail(issue)

for (const [path, baselineDigest] of [
  [mainHtmlPath, 'de5947193c09db99d96c55adf41010ee337cc15a0cb0d8dae92b8fb5e7f39031'],
  [labHtmlPath, 'd1a0fb3847e053c3d8443b3a5cf774fa3fcf519ee5c07d5e915510b19d2eabd9'],
]) {
  const source = readFileSync(path, 'utf8')
  for (const issue of validateHtmlReference(source)) fail(`${relative(repoDir, path)}: ${issue}`)
  if (digest(stripApprovedHtmlChange(source)) !== baselineDigest) fail(`${relative(repoDir, path)} changed outside the approved favicon link`)
}

const setupSource = readFileSync(appSetupPath, 'utf8')
for (const issue of validateSetupMapping(setupSource)) fail(issue)
for (const issue of validateSetupRouteOrdering(setupSource)) fail(issue)
if (digest(stripApprovedSetupChange(setupSource)) !== '09f804cd7fdf6b84fee7c3362c9533a88b10b0950dd19ad9f7a2e172b1d7c711') {
  fail('app/core/app_setup.py changed outside the approved favicon mapping')
}

const viteConfigSource = readFileSync(viteConfigPath, 'utf8')
for (const issue of validateViteConfig(viteConfigSource)) fail(issue)
for (const issue of validateViteDevelopmentMapping(viteConfigSource)) fail(issue)
if (digest(stripApprovedViteChange(viteConfigSource)) !== '789591098fb5c0a63de26e66934503a3df31c58e905966288eff8b70b18f81ec') {
  fail('frontend/vite.config.js changed outside the approved favicon hook')
}

const forbiddenAssetRoots = [join(repoDir, 'static'), join(frontendDir, 'src', 'assets')]
const duplicateAssetPaths = []
for (const root of forbiddenAssetRoots) {
  if (!existsSync(root)) continue
  for (const name of readdirSync(root, { recursive: true })) {
    if (/favicon\.(?:ico|png|svg|webp)$/i.test(String(name))) duplicateAssetPaths.push(relative(repoDir, join(root, String(name))))
  }
}
if (existsSync(join(frontendDir, 'public'))) {
  for (const issue of validateSourceFaviconInventory(readdirSync(join(frontendDir, 'public')), duplicateAssetPaths)) fail(issue)
}

const workaroundSources = [readFileSync(mainHtmlPath, 'utf8'), readFileSync(labHtmlPath, 'utf8'), setupSource].join('\n')
if (/page\.on\([^)]*console|console[^\n]*filter|route\.(?:abort|fulfill)|favicon[^\n]*(?:ignore|suppress)/i.test(workaroundSources)) {
  fail('favicon Console or network filtering workaround is forbidden')
}

const selfChecks = [
  validateAssetState({ sourceExists: false, buildExists: false }).some((issue) => issue.includes('source favicon')),
  validateHtmlReference('<link rel="icon" href="/v3/favicon.ico">').some((issue) => issue.includes('exactly /favicon.ico')),
  validateBuiltHtmlReference('<link rel="icon" href="/v3/favicon.ico" type="image/vnd.microsoft.icon">').some((issue) => issue.includes('absolute root favicon href')),
  validateBuiltHtmlReference('<link rel="icon" href="/favicon.ico" type="image/vnd.microsoft.icon"><script src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css">').some((issue) => issue.includes('/v3/ base')),
  validateIcoBuffer(Buffer.from('not-an-ico')).length > 0,
  validateIcoBuffer(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])).length > 0,
  validateAssetParity(Buffer.from('source'), Buffer.from('built')).some((issue) => issue.includes('size')),
  validateAssetParity(Buffer.from('source-a'), Buffer.from('source-b')).some((issue) => issue.includes('does not match')),
  validateSetupMapping('return FileResponse("index.html")').some((issue) => issue.includes('frontend/public/favicon.ico')),
  validateSetupRouteOrdering('@app.get("/v3/{path:path}", include_in_schema=False)\n@app.get("/favicon.ico", include_in_schema=False)').some((issue) => issue.includes('before the SPA fallback')),
  validateViteConfig(viteConfigSource.replace("base: '/v3/'", "base: '/'")).some((issue) => issue.includes('global base')),
  validateViteDevelopmentMapping('configureServer(server) {}').some((issue) => issue.includes('frontend/public/favicon.ico')),
  validateHtmlReference('<link rel="icon" href="/favicon.ico" type="image/vnd.microsoft.icon"><link rel="icon" href="/favicon.ico" type="image/vnd.microsoft.icon">').some((issue) => issue.includes('exactly one')),
  validateComponentTokenIsolation(':root { --v2-modal-gap: var(--v2-space-2); }').length === 0,
  validateComponentTokenIsolation(':root { --v2-favicon-color: red; --asset: url(/favicon.ico); }').length >= 2,
  validateSourceFaviconInventory(['favicon.ico', 'favicon.png'], ['static/favicon.ico']).some((issue) => issue.includes('only the shared favicon.ico')),
  validateProtectedDigest('changed', 'expected', 'frontend/src/views/ApiCasesView.vue').some((issue) => issue.includes('protected Phase 5.5D file changed')),
]
if (selfChecks.some((passed) => !passed)) fail('favicon validator self-check failed')

if (failures.length > 0) {
  console.error('V2 favicon static asset validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V2 favicon static asset validation passed (single ICO, exact HTML/Vite/FastAPI contracts, build parity, protected Phase 5.5D business files).')
