<template>
  <section
    v-bind="$attrs"
    class="v2-base-error-state"
    :class="{ 'v2-base-error-state--compact': compact }"
    :role="stateRole"
    :aria-labelledby="titleId"
    :aria-busy="busy || undefined"
  >
    <div v-if="$slots.icon" class="v2-base-error-state__icon" aria-hidden="true">
      <slot name="icon" />
    </div>
    <h2 :id="titleId" class="v2-base-error-state__title">{{ title }}</h2>
    <p v-if="message" class="v2-base-error-state__message">{{ message }}</p>
    <div v-if="$slots.details" class="v2-base-error-state__details">
      <slot name="details" />
    </div>
    <div
      v-if="$slots.action || (retryable && !$slots.action)"
      class="v2-base-error-state__action"
    >
      <slot v-if="$slots.action" name="action" />
      <BaseButton
        v-else-if="retryable && !$slots.action"
        variant="secondary"
        :loading="busy"
        :disabled="busy"
        @click="handleRetry"
      >
        {{ retryLabel }}
      </BaseButton>
    </div>
  </section>
</template>

<script setup>
import { computed, useId } from 'vue'
import BaseButton from './BaseButton.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  title: { type: String, required: true },
  message: { type: String, default: '' },
  retryable: { type: Boolean, default: false },
  retryLabel: { type: String, default: '重试' },
  busy: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['retry'])
const titleId = `v2-error-state-${useId()}-title`
const stateRole = computed(() => props.busy ? 'status' : 'alert')

function handleRetry() {
  if (props.busy) return
  emit('retry')
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--v2-error-state-gap);
    padding: var(--v2-error-state-padding);
    text-align: center;
  }

  .v2-base-error-state--compact {
    padding: var(--v2-error-state-padding-compact);
  }

  .v2-base-error-state__icon {
    width: var(--v2-error-state-icon-container-size);
    height: var(--v2-error-state-icon-container-size);
    display: grid;
    place-items: center;
    color: var(--v2-error-state-icon-text);
    background: var(--v2-error-state-icon-surface);
    border-radius: var(--v2-radius-round);
  }

  .v2-base-error-state__icon :deep(svg) {
    width: var(--v2-error-state-icon-size);
    height: var(--v2-error-state-icon-size);
  }

  .v2-base-error-state__title {
    max-width: var(--v2-error-state-content-max-width);
    margin: 0;
    color: var(--v2-error-state-title-text);
    font-size: var(--v2-error-state-title-size);
    line-height: var(--v2-line-height-heading);
  }

  .v2-base-error-state__message {
    max-width: var(--v2-error-state-content-max-width);
    margin: 0;
    color: var(--v2-error-state-message-text);
    font-size: var(--v2-error-state-message-size);
    line-height: var(--v2-line-height-body);
  }

  .v2-base-error-state__details {
    max-width: var(--v2-error-state-content-max-width);
    color: var(--v2-error-state-details-text);
    font-size: var(--v2-error-state-details-size);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-error-state__action {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--v2-error-state-gap);
    margin-top: var(--v2-space-1);
  }
}
</style>
