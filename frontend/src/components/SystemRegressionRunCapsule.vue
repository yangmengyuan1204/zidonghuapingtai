<template>
  <button
    v-if="visible"
    class="sr-capsule"
    :class="`sr-capsule--${tone}`"
    type="button"
    @click="goBack"
  >
    <span class="sr-capsule__dot" aria-hidden="true" />
    <span class="sr-capsule__copy">
      <b>{{ title }}</b>
      <span>{{ snapshot.done_count }}/{{ snapshot.total_count }}</span>
      <span>{{ clock }}</span>
    </span>
    <span class="sr-capsule__go">返回查看</span>
  </button>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getBatch } from '../api/modules/systemRegression.js'
import { navigateToView } from '../services/navigation.js'

const STORAGE_KEY = 'systemRegressionActiveBatch'
const LIVE = ['pending', 'running', 'waiting_account']

const route = useRoute()
const snapshot = ref(null)
const now = ref(Date.now())
let timer = 0
let clockTimer = 0

const onRegressionPage = computed(() => route.meta.viewKey === 'systemRegression' || route.name === 'systemRegression')
const live = computed(() => LIVE.includes(snapshot.value?.status))
const visible = computed(() => Boolean(snapshot.value?.id) && !onRegressionPage.value)
const tone = computed(() => (snapshot.value?.status === 'waiting_account' ? 'waiting' : live.value ? 'running' : 'done'))
const title = computed(() => {
  const status = snapshot.value?.status
  if (status === 'waiting_account') return '需要部长账号'
  if (LIVE.includes(status)) return '系统回归执行中'
  if (status === 'failed') return '批次已结束，有失败'
  if (status === 'stopped') return '批次已停止'
  return '批次已完成'
})
const clock = computed(() => {
  const started = Number(snapshot.value?.started_at || 0)
  const end = live.value ? now.value : Number(snapshot.value?.updated_at || now.value)
  const elapsed = started ? end - started : 0
  const total = Math.max(0, Math.floor(elapsed / 1000))
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
})

function readStored() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    return null
  }
}

function writeStored(batch) {
  if (!batch?.id) return
  const runs = batch.runs || []
  const done = runs.length
    ? runs.filter((run) => !LIVE.includes(run.status)).length
    : Number(batch.passed_count || 0) + Number(batch.failed_count || 0)
  const next = {
    id: batch.id,
    batch_no: batch.batch_no,
    status: batch.status,
    passed_count: Number(batch.passed_count || 0),
    failed_count: Number(batch.failed_count || 0),
    blocked_count: Number(batch.blocked_count || 0),
    total_count: Number(batch.total_count || runs.length || 0),
    done_count: done,
    started_at: snapshot.value?.started_at || Date.now(),
    updated_at: Date.now(),
  }
  snapshot.value = next
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

async function refresh() {
  const stored = readStored()
  if (!stored?.id) {
    snapshot.value = null
    return
  }
  snapshot.value = stored
  if (onRegressionPage.value) return
  if (!LIVE.includes(stored.status)) return
  try {
    const batch = await getBatch(stored.id)
    writeStored(batch)
  } catch (error) {
    if (String(error?.message || '').includes('不存在')) {
      localStorage.removeItem(STORAGE_KEY)
      snapshot.value = null
    }
  }
}

function onStorage(event) {
  if (event.key && event.key !== STORAGE_KEY) return
  snapshot.value = readStored()
}

function goBack() {
  navigateToView('systemRegression')
}

onMounted(() => {
  snapshot.value = readStored()
  window.addEventListener('storage', onStorage)
  timer = window.setInterval(refresh, 2000)
  clockTimer = window.setInterval(() => { now.value = Date.now() }, 1000)
  refresh()
})

onBeforeUnmount(() => {
  window.clearInterval(timer)
  window.clearInterval(clockTimer)
  window.removeEventListener('storage', onStorage)
})

watch(() => route.fullPath, refresh)
</script>

<style scoped>
.sr-capsule {
  display: inline-flex;
  height: 36px;
  align-items: center;
  gap: 10px;
  padding: 0 6px 0 12px;
  border: 1px solid #c5d4ff;
  border-radius: 999px;
  background: #edf2ff;
  color: #29343d;
  cursor: pointer;
}

.sr-capsule--waiting {
  border-color: #fdba74;
  background: #fff7ed;
}

.sr-capsule--done {
  border-color: #e2e8ee;
  background: #ffffff;
}

.sr-capsule__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #5d87ff;
}

.sr-capsule--running .sr-capsule__dot {
  animation: sr-pulse 1.4s ease-in-out infinite;
}

.sr-capsule--waiting .sr-capsule__dot {
  background: #c2410c;
  animation: sr-pulse 1.4s ease-in-out infinite;
}

.sr-capsule--done .sr-capsule__dot {
  background: #027a48;
}

.sr-capsule__copy {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
}

.sr-capsule__copy span {
  font-variant-numeric: tabular-nums;
  color: #7987a1;
}

.sr-capsule__go {
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: #5d87ff;
  color: #ffffff;
  font-size: 12px;
  line-height: 26px;
}

@keyframes sr-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (prefers-reduced-motion: reduce) {
  .sr-capsule__dot { animation: none; }
}
</style>
