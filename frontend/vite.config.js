import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const sharedFavicon = readFileSync(new URL('./public/favicon.ico', import.meta.url))

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
        const normalizedFavicon = html.replace(/<link\b[^>]*>/gi, (tag) => {
          const rel = tag.match(/\brel=(["'])(.*?)\1/i)?.[2].split(/\s+/) ?? []
          const href = tag.match(/\bhref=(["'])(.*?)\1/i)?.[2]
          if (!rel.includes('icon') || href !== '/v3/favicon.ico') return tag
          return tag.replace(/\bhref=(["'])\/v3\/favicon\.ico\1/i, 'href="/favicon.ico"')
        })
        return normalizedFavicon.replace(
          /src=(["'])\/v3\/static\/v2-theme-lock\.js([^"']*)\1/i,
          'src="/static/v2-theme-lock.js$2"',
        )
      },
    },
  }
}

// Vue3 迁移工程配置
// base 设为 /v3/，与 FastAPI 挂载路径一致
export default defineConfig({
  plugins: [vue(), preserveRootFaviconHref()],
  base: '/v3/',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
