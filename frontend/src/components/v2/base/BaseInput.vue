<template>
  <div
    class="v2-base-input"
    :class="{
      'v2-base-input--error': Boolean(error),
      'v2-base-input--disabled': disabled,
      'v2-base-input--readonly': readonly,
      'v2-base-input--filled': modelValue !== '' && modelValue !== null && modelValue !== undefined,
    }"
  >
    <label v-if="label" class="v2-base-input__label" :for="inputId">
      {{ label }}
      <span v-if="required" class="v2-base-input__required" aria-hidden="true">*</span>
    </label>

    <div class="v2-base-input__control">
      <span v-if="$slots.prefix" class="v2-base-input__affix">
        <slot name="prefix" />
      </span>
      <input
        v-bind="$attrs"
        :id="inputId"
        class="v2-base-input__native"
        :name="name"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :required="required"
        :autocomplete="autocomplete"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
        @input="handleInput"
        @focus="emit('focus', $event)"
        @blur="emit('blur', $event)"
        @change="emit('change', $event)"
      />
      <span v-if="$slots.suffix" class="v2-base-input__affix">
        <slot name="suffix" />
      </span>
    </div>

    <p v-if="error" :id="errorId" class="v2-base-input__message v2-base-input__message--error">
      {{ error }}
    </p>
    <p v-else-if="help" :id="helpId" class="v2-base-input__message">
      {{ help }}
    </p>
  </div>
</template>

<script setup>
import { computed, useAttrs, useId } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  id: { type: String, default: '' },
  name: { type: String, default: '' },
  type: { type: String, default: 'text' },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  help: { type: String, default: '' },
  error: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
  autocomplete: { type: String, default: undefined },
})

const emit = defineEmits(['update:modelValue', 'focus', 'blur', 'change'])
const attrs = useAttrs()
const generatedId = useId()
const inputId = computed(() => props.id || `v2-input-${generatedId}`)
const helpId = computed(() => `${inputId.value}-help`)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(() => {
  const ownDescription = props.error ? errorId.value : (props.help ? helpId.value : '')
  return [attrs['aria-describedby'], ownDescription].filter(Boolean).join(' ') || undefined
})

function handleInput(event) {
  emit('update:modelValue', event.target.value)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-input {
    display: grid;
    gap: var(--v2-input-label-gap);
    min-width: 0;
  }

  .v2-base-input__label {
    color: var(--v2-input-label-text);
    font-size: var(--v2-input-meta-font-size);
    font-weight: var(--v2-font-weight-semibold);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-input__required,
  .v2-base-input__message--error {
    color: var(--v2-input-error-text);
  }

  .v2-base-input__control {
    height: var(--v2-input-height);
    min-height: var(--v2-input-height);
    display: flex;
    align-items: center;
    gap: var(--v2-input-gap);
    padding: 0 var(--v2-input-padding);
    color: var(--v2-input-text);
    background: var(--v2-input-surface);
    border: var(--v2-border-width) solid var(--v2-input-border);
    border-radius: var(--v2-input-radius);
    box-shadow: none;
    transition:
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      box-shadow var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-input__control:hover {
    border-color: var(--v2-input-border-hover);
  }

  .v2-base-input__control:has(.v2-base-input__native:focus-visible) {
    border-color: var(--v2-input-border-focus);
    box-shadow: var(--v2-input-focus-ring);
  }

  .v2-base-input__native {
    width: 100%;
    min-width: 0;
    min-height: calc(var(--v2-input-height) - var(--v2-border-width) - var(--v2-border-width));
    padding: 0;
    color: inherit;
    background: var(--v2-color-overlay-transparent);
    border: 0;
    outline: 0;
    font-size: var(--v2-input-font-size);
    line-height: var(--v2-line-height-body);
  }

  .v2-base-input__native::placeholder {
    color: var(--v2-input-placeholder);
  }

  .v2-base-input__native:focus-visible {
    outline: none;
    box-shadow: none;
  }

  .v2-base-input__affix {
    display: inline-grid;
    place-items: center;
    flex: 0 0 auto;
    color: var(--v2-text-muted);
  }

  .v2-base-input__affix :deep(svg) {
    width: var(--v2-icon-size-sm);
    height: var(--v2-icon-size-sm);
  }

  .v2-base-input__message {
    margin: 0;
    color: var(--v2-input-help-text);
    font-size: var(--v2-input-meta-font-size);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-input--filled .v2-base-input__control {
    border-color: var(--v2-input-border-hover);
  }

  .v2-base-input--error .v2-base-input__control {
    border-color: var(--v2-input-border-error);
  }

  .v2-base-input--disabled .v2-base-input__control {
    color: var(--v2-input-disabled-text);
    background: var(--v2-input-surface-disabled);
    opacity: var(--v2-input-disabled-opacity);
  }

  .v2-base-input--readonly .v2-base-input__control {
    background: var(--v2-input-surface-readonly);
  }
}
</style>
