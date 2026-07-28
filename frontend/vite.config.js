import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vue3 迁移工程配置
// base 设为 /v3/，与 FastAPI 挂载路径一致
export default defineConfig({
  plugins: [vue()],
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
