<template>
  <nav
    v-bind="$attrs"
    class="v2-base-pagination"
    :aria-label="ariaLabel"
  >
    <button
      class="v2-base-pagination__control v2-base-pagination__control--direction"
      type="button"
      aria-label="上一页"
      :disabled="previousDisabled"
      @click="requestPage(currentPage - 1)"
    >
      <span aria-hidden="true">‹</span>
    </button>

    <template v-for="item in paginationItems" :key="item">
      <button
        v-if="typeof item === 'number'"
        class="v2-base-pagination__control"
        :class="{ 'v2-base-pagination__control--current': item === currentPage }"
        type="button"
        :aria-label="`第 ${item} 页`"
        :aria-current="item === currentPage ? 'page' : undefined"
        :disabled="disabled"
        @click="requestPage(item)"
      >
        {{ item }}
      </button>
      <span
        v-else
        class="v2-base-pagination__ellipsis"
        aria-hidden="true"
      >
        …
      </span>
    </template>

    <button
      class="v2-base-pagination__control v2-base-pagination__control--direction"
      type="button"
      aria-label="下一页"
      :disabled="nextDisabled"
      @click="requestPage(currentPage + 1)"
    >
      <span aria-hidden="true">›</span>
    </button>
  </nav>
</template>

<script setup>
import { computed } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  page: { type: Number, default: 1 },
  total: { type: Number, default: 0 },
  pageSize: { type: Number, default: 20 },
  siblingCount: { type: Number, default: 1 },
  disabled: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '分页导航' },
})

const emit = defineEmits(['change'])

const totalPages = computed(() => {
  const total = Number.isFinite(props.total) ? Math.max(0, props.total) : 0
  const pageSize = Number.isFinite(props.pageSize) ? Math.max(1, props.pageSize) : 1
  return Math.max(1, Math.ceil(total / pageSize))
})

const currentPage = computed(() => {
  const page = Number.isFinite(props.page) ? Math.floor(props.page) : 1
  return Math.min(totalPages.value, Math.max(1, page))
})

const paginationItems = computed(() =>
  buildPaginationItems(totalPages.value, currentPage.value, props.siblingCount)
)
const previousDisabled = computed(() => props.disabled || currentPage.value <= 1)
const nextDisabled = computed(() => props.disabled || currentPage.value >= totalPages.value)

function buildPaginationItems(total, current, siblingCount) {
  const siblings = Number.isFinite(siblingCount) ? Math.max(0, Math.floor(siblingCount)) : 1
  const visibleLimit = siblings * 2 + 5
  if (total <= visibleLimit) {
    return Array.from({ length: total }, (_, index) => index + 1)
  }

  const pageSet = new Set([1, total])
  for (let page = current - siblings; page <= current + siblings; page += 1) {
    if (page > 1 && page < total) pageSet.add(page)
  }

  const pages = [...pageSet].sort((left, right) => left - right)
  const items = []
  for (let index = 0; index < pages.length; index += 1) {
    const page = pages[index]
    const previous = pages[index - 1]
    if (previous !== undefined) {
      const gap = page - previous
      if (gap === 2) items.push(previous + 1)
      if (gap > 2) items.push(`ellipsis-${previous}-${page}`)
    }
    items.push(page)
  }
  return items
}

function requestPage(targetPage) {
  if (props.disabled) return
  if (targetPage < 1 || targetPage > totalPages.value) return
  if (targetPage === currentPage.value) return
  emit('change', targetPage)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-pagination {
    min-height: var(--v2-pagination-height);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--v2-pagination-gap);
  }

  .v2-base-pagination__control {
    min-width: var(--v2-pagination-control-size);
    height: var(--v2-pagination-control-size);
    display: inline-grid;
    place-items: center;
    padding: 0 var(--v2-pagination-gap);
    color: var(--v2-pagination-text);
    background: var(--v2-pagination-surface);
    border: var(--v2-border-width) solid var(--v2-pagination-border);
    border-radius: var(--v2-pagination-radius);
    font-size: var(--v2-pagination-font-size);
    font-weight: var(--v2-pagination-font-weight);
    line-height: var(--v2-line-height-tight);
    cursor: pointer;
    transition:
      color var(--v2-motion-duration) var(--v2-motion-easing),
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      opacity var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-pagination__control:hover:not(:disabled) {
    color: var(--v2-pagination-text-hover);
    background: var(--v2-pagination-surface-hover);
    border-color: var(--v2-pagination-border-hover);
  }

  .v2-base-pagination__control:active:not(:disabled) {
    background: var(--v2-pagination-surface-pressed);
  }

  .v2-base-pagination__control:focus-visible {
    outline: none;
    box-shadow: var(--v2-pagination-focus-ring);
  }

  .v2-base-pagination__control:disabled {
    color: var(--v2-pagination-text-disabled);
    background: var(--v2-pagination-surface-disabled);
    cursor: not-allowed;
    opacity: var(--v2-pagination-disabled-opacity);
  }

  .v2-base-pagination__control--current,
  .v2-base-pagination__control--current:hover:not(:disabled) {
    color: var(--v2-pagination-text-active);
    background: var(--v2-pagination-surface-active);
    border-color: var(--v2-pagination-surface-active);
  }

  .v2-base-pagination__control--direction {
    font-size: var(--v2-font-size-body);
  }

  .v2-base-pagination__ellipsis {
    min-width: var(--v2-pagination-control-size);
    height: var(--v2-pagination-control-size);
    display: inline-grid;
    place-items: center;
    color: var(--v2-pagination-text);
    font-size: var(--v2-pagination-font-size);
  }
}
</style>
