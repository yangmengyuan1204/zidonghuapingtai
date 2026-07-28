/**
 * Theme store — 主题切换
 * 对齐旧应用 app.js#L109-L112 的 initTheme + app.js#L129 的 .theme-dot 切换
 * 共享 localStorage 'theme' key，与旧应用同源
 *
 * 4 个主题：shuimo(水墨) / zhuanye(专业蓝灰) / qingxuan(清爽浅色) / xiaolan(小兰)
 * 注意：styles.css 中 zhuanye 无单独 [data-theme] 块，使用 :root 默认变量（专业蓝灰配色）
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

const VALID_THEMES = ['shuimo', 'zhuanye', 'qingxuan', 'xiaolan']

export const useThemeStore = defineStore('theme', () => {
  const theme = ref(localStorage.getItem('theme') || 'shuimo')

  function applyTheme(t) {
    if (VALID_THEMES.includes(t)) {
      theme.value = t
      localStorage.setItem('theme', t)
      document.documentElement.dataset.theme = t
    }
  }

  // 初始化时应用主题
  applyTheme(theme.value)

  return { theme, applyTheme, VALID_THEMES }
})
