<template>
  <div class="v2-legacy-embed">
    <iframe
      ref="frameEl"
      class="v2-legacy-embed__frame"
      :title="frameTitle"
      :src="embedSrc"
      @load="onFrameLoad"
    />
  </div>
</template>

<script setup>
/**
 * Legacy 页面壳层桥接：在 V2 AppShell 内嵌同一源旧应用，
 * 通过 ?v3_embed=1 跳过 migration-bridge 重定向，并隐藏旧侧栏/顶栏。
 */
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { menuViews } from '../router/index.js'

const EMBED_STYLE_ID = 'v3-embed-style'
const EMBED_STYLE = `
html.v3-embed,
html.v3-embed body {
  height: 100%;
  overflow-x: hidden;
  overflow-y: auto; /* 保留右侧滚动条，避免长页面无法滚动 */
  background: transparent;
}
html.v3-embed body::before {
  display: none !important;
}
html.v3-embed .shell {
  min-height: 100%;
  grid-template-columns: minmax(0, 1fr);
}
html.v3-embed .sidebar,
html.v3-embed .topbar {
  display: none !important;
}
html.v3-embed .main {
  min-width: 0;
  min-height: 100%;
}
html.v3-embed .content {
  padding: 0;
}
`

const route = useRoute()
const frameEl = ref(null)

const viewKey = computed(() => String(route.meta.viewKey || ''))

const frameTitle = computed(() => {
  const item = menuViews.find((view) => view.key === viewKey.value)
  return item?.label || 'Legacy 页面'
})

const embedSrc = computed(() => {
  if (!viewKey.value) return 'about:blank'
  return `/?v3_embed=1#/${viewKey.value}`
})

function applyEmbedChrome(doc) {
  if (!doc?.documentElement) return
  doc.documentElement.classList.add('v3-embed')
  if (doc.getElementById(EMBED_STYLE_ID)) return
  const style = doc.createElement('style')
  style.id = EMBED_STYLE_ID
  style.textContent = EMBED_STYLE
  doc.head?.appendChild(style)
}

function onFrameLoad() {
  try {
    applyEmbedChrome(frameEl.value?.contentDocument)
  } catch {
    // cross-origin or unavailable document — ignore
  }
}
</script>

<style scoped>
@layer v2-overrides {
  .v2-legacy-embed {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: calc(100vh - 160px);
    min-height: calc(100dvh - 160px);
  }

  .v2-legacy-embed__frame {
    flex: 1 1 auto;
    width: 100%;
    min-height: calc(100vh - 160px);
    min-height: calc(100dvh - 160px);
    border: 0;
    background: transparent;
  }
}
</style>
