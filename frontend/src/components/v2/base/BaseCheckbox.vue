<template>
  <label
    class="v2-base-checkbox"
    :class="{ 'v2-base-checkbox--disabled': disabled }"
    :for="inputId"
  >
    <input
      v-bind="$attrs"
      :id="inputId"
      ref="inputEl"
      type="checkbox"
      class="v2-base-checkbox__native"
      :name="name"
      :checked="modelValue"
      :disabled="disabled"
      :required="required"
      :aria-describedby="describedBy"
      @change="handleChange"
    />
    <span v-if="label || description" class="v2-base-checkbox__copy">
      <span v-if="label" class="v2-base-checkbox__label">{{ label }}</span>
      <span v-if="description" :id="descriptionId" class="v2-base-checkbox__description">
        {{ description }}
      </span>
    </span>
  </label>
</template>

<script setup>
import { computed, onMounted, onUpdated, ref, useAttrs, useId, watch } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  id: { type: String, default: '' },
  label: { type: String, default: '' },
  description: { type: String, default: '' },
  name: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
  indeterminate: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'change'])
const attrs = useAttrs()
const generatedId = useId()
const inputEl = ref(null)
const inputId = computed(() => props.id || `v2-checkbox-${generatedId}`)
const descriptionId = computed(() => `${inputId.value}-description`)
const describedBy = computed(() =>
  [attrs['aria-describedby'], props.description ? descriptionId.value : '']
    .filter(Boolean)
    .join(' ') || undefined
)

function syncIndeterminate() {
  if (inputEl.value) {
    inputEl.value.indeterminate = Boolean(props.indeterminate)
  }
}

function handleChange(event) {
  if (props.disabled) return
  emit('update:modelValue', event.target.checked)
  emit('change', event)
}

onMounted(syncIndeterminate)
onUpdated(syncIndeterminate)
watch(() => props.indeterminate, syncIndeterminate)
</script>

<style scoped>
@layer v2-components {
  .v2-base-checkbox {
    display: inline-flex;
    align-items: flex-start;
    gap: var(--v2-checkbox-gap);
    color: var(--v2-checkbox-label-text);
    font-size: var(--v2-checkbox-font-size);
    line-height: var(--v2-line-height-body);
    cursor: pointer;
  }

  .v2-base-checkbox__native {
    width: var(--v2-checkbox-size);
    height: var(--v2-checkbox-size);
    flex: 0 0 auto;
    margin: var(--v2-space-micro) 0 0;
    border-radius: var(--v2-checkbox-radius);
    accent-color: var(--v2-checkbox-selected-surface);
    cursor: inherit;
  }

  .v2-base-checkbox__native:focus-visible {
    outline: none;
    box-shadow: var(--v2-checkbox-focus-ring);
  }

  .v2-base-checkbox__copy {
    display: grid;
    gap: var(--v2-checkbox-description-gap);
    min-width: 0;
  }

  .v2-base-checkbox__label {
    color: var(--v2-checkbox-label-text);
  }

  .v2-base-checkbox__description {
    color: var(--v2-checkbox-description-text);
    font-size: var(--v2-checkbox-description-font-size);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-checkbox--disabled {
    cursor: not-allowed;
    opacity: var(--v2-checkbox-disabled-opacity);
  }
}
</style>
