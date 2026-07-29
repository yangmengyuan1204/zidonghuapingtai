<template>
  <div
    v-bind="$attrs"
    class="v2-base-skeleton"
    :class="[
      `v2-base-skeleton--${variant}`,
      { 'v2-base-skeleton--animated': animated },
    ]"
    :style="rootStyle"
    aria-hidden="true"
  >
    <template v-if="variant === 'text'">
      <span
        v-for="line in normalizedLines"
        :key="line"
        class="v2-base-skeleton__item v2-base-skeleton__item--text"
        :class="{ 'v2-base-skeleton__item--last': normalizedLines > 1 && line === normalizedLines }"
        :style="textLineStyle"
      ></span>
    </template>
    <span
      v-else
      class="v2-base-skeleton__item"
      :class="`v2-base-skeleton__item--${variant}`"
      :style="shapeStyle"
    ></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  variant: {
    type: String,
    default: 'text',
    validator: (value) => ['text', 'circle', 'rectangle'].includes(value),
  },
  width: { type: [String, Number], default: undefined },
  height: { type: [String, Number], default: undefined },
  lines: { type: Number, default: 1 },
  animated: { type: Boolean, default: true },
})

const normalizedLines = computed(() => {
  if (!Number.isFinite(props.lines)) return 1
  return Math.max(1, Math.floor(props.lines))
})
const normalizedWidth = computed(() => normalizeDimension(props.width))
const normalizedHeight = computed(() => normalizeDimension(props.height))

const rootStyle = computed(() => {
  if (props.variant === 'circle') {
    const size = normalizedWidth.value || normalizedHeight.value
    return {
      width: size,
      height: size,
    }
  }
  return { width: normalizedWidth.value }
})

const textLineStyle = computed(() => ({
  height: normalizedHeight.value,
}))

const shapeStyle = computed(() => ({
  height: props.variant === 'rectangle' ? normalizedHeight.value : undefined,
}))

function normalizeDimension(value) {
  if (typeof value === 'number') return `${Math.max(0, value)}px`
  if (typeof value !== 'string') return undefined
  const dimension = value.trim()
  if (!dimension) return undefined
  return /^-/.test(dimension) ? '0px' : dimension
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-skeleton {
    width: 100%;
    display: grid;
    gap: var(--v2-skeleton-line-gap);
  }

  .v2-base-skeleton--circle {
    width: var(--v2-skeleton-circle-size);
    height: var(--v2-skeleton-circle-size);
    display: inline-flex;
  }

  .v2-base-skeleton__item {
    display: block;
    width: 100%;
    overflow: hidden;
    background: var(--v2-skeleton-surface);
    border-radius: var(--v2-skeleton-radius);
  }

  .v2-base-skeleton__item--text {
    height: var(--v2-skeleton-text-height);
  }

  .v2-base-skeleton__item--last {
    width: calc(100% - var(--v2-space-6));
  }

  .v2-base-skeleton__item--circle {
    height: 100%;
    border-radius: var(--v2-radius-round);
  }

  .v2-base-skeleton__item--rectangle {
    height: var(--v2-skeleton-rectangle-height);
  }

  .v2-base-skeleton--animated .v2-base-skeleton__item {
    background-image: linear-gradient(
      90deg,
      var(--v2-skeleton-surface),
      var(--v2-skeleton-highlight),
      var(--v2-skeleton-surface)
    );
    background-size: 200% 100%;
    animation:
      v2-skeleton-shimmer
      var(--v2-skeleton-duration)
      var(--v2-skeleton-easing)
      infinite;
  }

  @keyframes v2-skeleton-shimmer {
    from {
      background-position: 100% 0;
    }

    to {
      background-position: -100% 0;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .v2-base-skeleton--animated .v2-base-skeleton__item {
      animation: none;
    }
  }
}
</style>
