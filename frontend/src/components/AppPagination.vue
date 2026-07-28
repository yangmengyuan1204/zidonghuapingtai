<template>
  <div v-if="totalPages > 1" class="pagination">
    <button
      v-for="p in pageList"
      :key="p"
      class="page-btn"
      :class="{ active: p === current }"
      :disabled="p === '...'"
      @click="p !== '...' && $emit('change', p)"
    >
      {{ p === '...' ? '…' : p }}
    </button>
  </div>
</template>

<script setup>
/**
 * 通用分页组件
 * 对齐旧应用 records 页的 .page-btn 分页逻辑（pageSize=20）
 */
import { computed } from 'vue'

const props = defineProps({
  current: { type: Number, default: 1 },
  total: { type: Number, default: 0 },
  pageSize: { type: Number, default: 20 },
})

defineEmits(['change'])

const totalPages = computed(() => Math.ceil(props.total / props.pageSize) || 1)

const pageList = computed(() => {
  const total = totalPages.value
  const cur = props.current
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  const pages = [1]
  if (cur > 3) pages.push('...')
  const start = Math.max(2, cur - 1)
  const end = Math.min(total - 1, cur + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  if (cur < total - 2) pages.push('...')
  pages.push(total)
  return pages
})
</script>

<style scoped>
.pagination {
  display: flex;
  gap: 4px;
  justify-content: center;
  margin-top: 12px;
}
.page-btn {
  min-width: 32px;
  height: 32px;
  border: 1px solid var(--line, #e2e5ed);
  border-radius: 6px;
  background: var(--surface-solid, #fff);
  cursor: pointer;
  font-size: 13px;
}
.page-btn.active {
  background: var(--accent, #6366f1);
  color: #fff;
  border-color: var(--accent, #6366f1);
}
.page-btn:disabled {
  cursor: default;
  border: none;
}
</style>
