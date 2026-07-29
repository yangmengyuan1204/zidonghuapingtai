/**
 * Theme store — Forest Light product theme (V2 Phase 1)
 *
 * - localStorage key 仍为 'theme'（禁止改名）
 * - 产品层唯一主题：forest-light
 * - 旧值 shuimo/zhuanye/qingxuan/xiaolan 自动映射到 forest-light
 * - 旧主题 CSS 块保留在 styles.css，仅作兼容；产品层不可切换
 * - Dark Mode：V3
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const PRODUCT_THEME = 'forest-light'

/** 历史主题值（兼容读取，写入时一律映射为 PRODUCT_THEME） */
export const LEGACY_THEME_VALUES = ['shuimo', 'zhuanye', 'qingxuan', 'xiaolan']

const VALID_THEMES = [PRODUCT_THEME, ...LEGACY_THEME_VALUES]

function normalizeTheme(value) {
  if (!value) return PRODUCT_THEME
  if (value === PRODUCT_THEME) return PRODUCT_THEME
  if (LEGACY_THEME_VALUES.includes(value)) return PRODUCT_THEME
  return PRODUCT_THEME
}

export const useThemeStore = defineStore('theme', () => {
  const theme = ref(PRODUCT_THEME)

  function applyTheme(t) {
    const next = VALID_THEMES.includes(t) ? normalizeTheme(t) : PRODUCT_THEME
    theme.value = next
    localStorage.setItem('theme', next)
    document.documentElement.dataset.theme = next
  }

  // 启动时：读取旧值并锁定为 Forest Light
  applyTheme(localStorage.getItem('theme') || PRODUCT_THEME)

  return {
    theme,
    applyTheme,
    PRODUCT_THEME,
    LEGACY_THEME_VALUES,
    /** @deprecated 产品层不再暴露多主题；保留字段避免外部引用报错 */
    VALID_THEMES: [PRODUCT_THEME],
  }
})
