<template>
  <div
    class="v2-base-select"
    :class="{
      'v2-base-select--error': Boolean(error),
      'v2-base-select--disabled': disabled,
      'v2-base-select--filled': modelValue !== '' && modelValue !== null && modelValue !== undefined,
    }"
  >
    <label v-if="label" class="v2-base-select__label" :for="selectId">
      {{ label }}
      <span v-if="required" class="v2-base-select__required" aria-hidden="true">*</span>
    </label>

    <select
      v-bind="$attrs"
      :id="selectId"
      class="v2-base-select__native"
      :name="name"
      :value="modelValue"
      :disabled="disabled"
      :required="required"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      @change="handleChange"
      @focus="emit('focus', $event)"
      @blur="emit('blur', $event)"
    >
      <option v-if="placeholder" value="" :disabled="required">
        {{ placeholder }}
      </option>
      <option
        v-for="(option, index) in options"
        :key="optionKey(option, index)"
        :value="resolveOptionValue(option)"
        :disabled="resolveOptionDisabled(option)"
      >
        {{ resolveOptionLabel(option) }}
      </option>
    </select>

    <p v-if="error" :id="errorId" class="v2-base-select__message v2-base-select__message--error">
      {{ error }}
    </p>
    <p v-else-if="help" :id="helpId" class="v2-base-select__message">
      {{ help }}
    </p>
  </div>
</template>

<script setup>
import { computed, useAttrs, useId } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: '' },
  id: { type: String, default: '' },
  name: { type: String, default: '' },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  help: { type: String, default: '' },
  error: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
  options: { type: Array, default: () => [] },
  optionValue: { type: String, default: 'value' },
  optionLabel: { type: String, default: 'label' },
})

const emit = defineEmits(['update:modelValue', 'change', 'focus', 'blur'])
const attrs = useAttrs()
const generatedId = useId()
const selectId = computed(() => props.id || `v2-select-${generatedId}`)
const helpId = computed(() => `${selectId.value}-help`)
const errorId = computed(() => `${selectId.value}-error`)
const describedBy = computed(() => {
  const ownDescription = props.error ? errorId.value : (props.help ? helpId.value : '')
  return [attrs['aria-describedby'], ownDescription].filter(Boolean).join(' ') || undefined
})

function isOptionObject(option) {
  return option !== null && typeof option === 'object' && !Array.isArray(option)
}

function resolveOptionValue(option) {
  return isOptionObject(option) ? option[props.optionValue] : option
}

function resolveOptionLabel(option) {
  return isOptionObject(option) ? option[props.optionLabel] : option
}

function resolveOptionDisabled(option) {
  return isOptionObject(option) && Boolean(option.disabled)
}

function optionKey(option, index) {
  return `${String(resolveOptionValue(option))}-${index}`
}

function handleChange(event) {
  const selectedOption = event.target.options[event.target.selectedIndex]
  emit('update:modelValue', selectedOption?._value ?? event.target.value)
  emit('change', event)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-select {
    display: grid;
    gap: var(--v2-select-label-gap);
    min-width: 0;
  }

  .v2-base-select__label {
    color: var(--v2-select-label-text);
    font-size: var(--v2-select-meta-font-size);
    font-weight: var(--v2-font-weight-semibold);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-select__required,
  .v2-base-select__message--error {
    color: var(--v2-select-error-text);
  }

  .v2-base-select__native {
    width: 100%;
    min-width: 0;
    height: var(--v2-select-height);
    padding: 0 var(--v2-select-padding);
    color: var(--v2-select-text);
    background: var(--v2-select-surface);
    border: var(--v2-border-width) solid var(--v2-select-border);
    border-radius: var(--v2-select-radius);
    outline: none;
    font-size: var(--v2-select-font-size);
    line-height: var(--v2-line-height-body);
    transition:
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      box-shadow var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-select__native:hover:not(:disabled) {
    border-color: var(--v2-select-border-hover);
  }

  .v2-base-select__native:focus-visible {
    border-color: var(--v2-select-border-focus);
    box-shadow: var(--v2-select-focus-ring);
  }

  .v2-base-select__message {
    margin: 0;
    color: var(--v2-select-help-text);
    font-size: var(--v2-select-meta-font-size);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-select--filled .v2-base-select__native {
    border-color: var(--v2-select-border-hover);
  }

  .v2-base-select--error .v2-base-select__native {
    border-color: var(--v2-select-border-error);
  }

  .v2-base-select--disabled .v2-base-select__native {
    color: var(--v2-select-disabled-text);
    background: var(--v2-select-surface-disabled);
    cursor: not-allowed;
    opacity: var(--v2-select-disabled-opacity);
  }
}
</style>
