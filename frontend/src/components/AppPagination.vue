<template>
  <BasePagination
    v-if="totalPages > 1"
    :page="current"
    :total="total"
    :page-size="pageSize"
    aria-label="分页导航"
    @change="$emit('change', $event)"
  />
</template>

<script setup>
/**
 * 通用分页组件
 * 对齐旧应用 records 页的 .page-btn 分页逻辑（pageSize=20）
 */
import { computed } from 'vue'
import { BasePagination } from './v2/base/index.js'

const props = defineProps({
  current: { type: Number, default: 1 },
  total: { type: Number, default: 0 },
  pageSize: { type: Number, default: 20 },
})

defineEmits(['change'])

const totalPages = computed(() => Math.ceil(props.total / props.pageSize) || 1)

</script>

<style scoped>
</style>
