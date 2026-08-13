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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { menuViews } from '../router/index.js'
import { useToastStore } from '../stores/toast.js'

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
const router = useRouter()
const toast = useToastStore()
const frameEl = ref(null)
const openedRerunRecordId = ref('')
const openingRerunRecordId = ref('')
const frameReady = ref(false)
const bridgeGeneration = ref(0)

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

function waitForRerunModule(frameWindow, attempts = 20) {
  return new Promise((resolve, reject) => {
    let remaining = attempts
    const check = () => {
      if (frameWindow?.TestRecordRerun?.open) {
        resolve(frameWindow.TestRecordRerun)
        return
      }
      remaining -= 1
      if (remaining <= 0) {
        reject(new Error('TestRecordRerun module unavailable'))
        return
      }
      window.setTimeout(check, 100)
    }
    check()
  })
}

function frameMatchesCurrentView(frameWindow) {
  try {
    return frameWindow?.location?.hash === `#/${viewKey.value}`
  } catch {
    return false
  }
}

function invalidateRerunBridge() {
  bridgeGeneration.value += 1
  frameReady.value = false
  openedRerunRecordId.value = ''
  openingRerunRecordId.value = ''
}

function isCurrentRerunTask(task) {
  return bridgeGeneration.value === task.generation
    && route.name === task.routeName
    && viewKey.value === 'dataScripts'
    && String(route.query.rerun_record_id || '').trim() === task.recordId
    && frameEl.value?.contentWindow === task.frameWindow
    && frameMatchesCurrentView(task.frameWindow)
}

async function openPendingRerun() {
  const recordId = String(route.query.rerun_record_id || '').trim()
  if (!frameReady.value || !recordId) return
  if (openedRerunRecordId.value === recordId || openingRerunRecordId.value === recordId) return
  openingRerunRecordId.value = recordId
  const task = {
    generation: bridgeGeneration.value,
    recordId,
    routeName: route.name,
    frameWindow: frameEl.value?.contentWindow,
  }
  try {
    const rerunModule = await waitForRerunModule(task.frameWindow)
    if (!isCurrentRerunTask(task)) return
    await rerunModule.open(Number(recordId))
    if (!isCurrentRerunTask(task)) return
    openedRerunRecordId.value = recordId
    const nextQuery = { ...route.query }
    delete nextQuery.rerun_record_id
    await router.replace({ name: task.routeName, query: nextQuery })
  } catch {
    if (isCurrentRerunTask(task)) {
      toast.show('数据工厂执行表单加载失败，请刷新后重试')
    }
  } finally {
    if (bridgeGeneration.value === task.generation && openingRerunRecordId.value === recordId) {
      openingRerunRecordId.value = ''
    }
  }
}

function onFrameLoad() {
  try {
    const frameWindow = frameEl.value?.contentWindow
    if (!frameMatchesCurrentView(frameWindow)) return
    applyEmbedChrome(frameEl.value?.contentDocument)
    frameReady.value = true
    openPendingRerun()
  } catch {
    toast.show('数据工厂页面加载失败，请刷新后重试')
  }
}

watch(viewKey, invalidateRerunBridge, { flush: 'sync' })
watch(() => route.query.rerun_record_id, openPendingRerun)
onBeforeUnmount(invalidateRerunBridge)
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
