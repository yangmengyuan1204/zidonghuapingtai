<template>
  <section
    v-bind="$attrs"
    class="v2-base-empty-state"
    :class="{ 'v2-base-empty-state--compact': compact }"
    :aria-labelledby="titleId"
  >
    <div
      v-if="$slots.icon && !iconHidden"
      class="v2-base-empty-state__icon"
      aria-hidden="true"
    >
      <slot name="icon" />
    </div>
    <h2 :id="titleId" class="v2-base-empty-state__title">{{ title }}</h2>
    <p v-if="description" class="v2-base-empty-state__description">
      {{ description }}
    </p>
    <div v-if="$slots.default" class="v2-base-empty-state__content">
      <slot />
    </div>
    <div v-if="$slots.action" class="v2-base-empty-state__action">
      <slot name="action" />
    </div>
  </section>
</template>

<script setup>
import { useId } from 'vue'

defineOptions({ inheritAttrs: false })

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  compact: { type: Boolean, default: false },
  iconHidden: { type: Boolean, default: false },
})

const titleId = `v2-empty-state-${useId()}-title`
</script>

<style scoped>
@layer v2-components {
  .v2-base-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--v2-empty-state-gap);
    padding: var(--v2-empty-state-padding);
    text-align: center;
  }

  .v2-base-empty-state--compact {
    padding: var(--v2-empty-state-padding-compact);
  }

  .v2-base-empty-state__icon {
    width: var(--v2-empty-state-icon-container-size);
    height: var(--v2-empty-state-icon-container-size);
    display: grid;
    place-items: center;
    color: var(--v2-empty-state-icon-text);
    background: var(--v2-empty-state-icon-surface);
    border-radius: var(--v2-radius-round);
  }

  .v2-base-empty-state__icon :deep(svg) {
    width: var(--v2-empty-state-icon-size);
    height: var(--v2-empty-state-icon-size);
  }

  .v2-base-empty-state__title {
    max-width: var(--v2-empty-state-content-max-width);
    margin: 0;
    color: var(--v2-empty-state-title-text);
    font-size: var(--v2-empty-state-title-size);
    line-height: var(--v2-line-height-heading);
  }

  .v2-base-empty-state__description,
  .v2-base-empty-state__content {
    max-width: var(--v2-empty-state-content-max-width);
    margin: 0;
    color: var(--v2-empty-state-description-text);
    font-size: var(--v2-empty-state-description-size);
    line-height: var(--v2-line-height-body);
  }

  .v2-base-empty-state__action {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--v2-empty-state-gap);
    margin-top: var(--v2-space-1);
  }
}
</style>
