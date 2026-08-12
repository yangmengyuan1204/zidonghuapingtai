<template>
  <div
    class="v2-base-textarea"
    :class="{
      'v2-base-textarea--error': Boolean(error),
      'v2-base-textarea--disabled': disabled,
      'v2-base-textarea--readonly': readonly,
    }"
  >
    <label v-if="label" class="v2-base-textarea__label" :for="textareaId">
      {{ label }}
      <span v-if="required" class="v2-base-textarea__required" aria-hidden="true">*</span>
    </label>

    <textarea
      v-bind="$attrs"
      :id="textareaId"
      class="v2-base-textarea__native"
      :name="name"
      :value="modelValue"
      :rows="rows"
      :maxlength="maxlength"
      :placeholder="placeholder"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      @input="handleInput"
      @change="emit('change', $event)"
      @focus="emit('focus', $event)"
      @blur="emit('blur', $event)"
    />

    <div v-if="error || help || hasMaxlength" class="v2-base-textarea__meta">
      <p v-if="error" :id="errorId" class="v2-base-textarea__message v2-base-textarea__message--error">
        {{ error }}
      </p>
      <p v-else-if="help" :id="helpId" class="v2-base-textarea__message">
        {{ help }}
      </p>
      <span
        v-if="hasMaxlength"
        :id="counterId"
        class="v2-base-textarea__counter"
      >{{ currentLength }} / {{ maxlength }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, useAttrs, useId } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  id: { type: String, default: '' },
  name: { type: String, default: '' },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  help: { type: String, default: '' },
  error: { type: String, default: '' },
  rows: { type: Number, default: 4 },
  maxlength: { type: Number, default: undefined },
  disabled: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'change', 'focus', 'blur'])
const attrs = useAttrs()
const generatedId = useId()
const textareaId = computed(() => props.id || `v2-textarea-${generatedId}`)
const helpId = computed(() => `${textareaId.value}-help`)
const errorId = computed(() => `${textareaId.value}-error`)
const counterId = computed(() => `${textareaId.value}-counter`)
const hasMaxlength = computed(() => Number.isFinite(props.maxlength) && props.maxlength >= 0)
const currentLength = computed(() => String(props.modelValue ?? '').length)
const describedBy = computed(() => {
  const ownDescription = props.error ? errorId.value : (props.help ? helpId.value : '')
  const counterDescription = hasMaxlength.value ? counterId.value : ''
  return [attrs['aria-describedby'], ownDescription, counterDescription].filter(Boolean).join(' ') || undefined
})

function handleInput(event) {
  emit('update:modelValue', event.target.value)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-textarea {
    display: grid;
    gap: var(--v2-textarea-label-gap);
    min-width: 0;
  }

  .v2-base-textarea__label {
    color: var(--v2-textarea-label-text);
    font-size: var(--v2-textarea-meta-font-size);
    font-weight: var(--v2-font-weight-semibold);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-textarea__required,
  .v2-base-textarea__message--error {
    color: var(--v2-textarea-error-text);
  }

  .v2-base-textarea__native {
    width: 100%;
    min-width: 0;
    min-height: var(--v2-textarea-min-height);
    padding: 10px var(--v2-textarea-padding);
    color: var(--v2-textarea-text);
    background: var(--v2-textarea-surface);
    border: var(--v2-border-width) solid var(--v2-textarea-border);
    border-radius: var(--v2-textarea-radius);
    outline: none;
    font: inherit;
    font-size: var(--v2-textarea-font-size);
    line-height: var(--v2-line-height-body);
    resize: vertical;
    box-shadow: none;
    transition:
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      box-shadow var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-textarea__native::placeholder {
    color: var(--v2-textarea-placeholder);
  }

  .v2-base-textarea__native:hover:not(:disabled) {
    border-color: var(--v2-textarea-border-hover);
  }

  .v2-base-textarea__native:focus-visible {
    border-color: var(--v2-textarea-border-focus);
    box-shadow: var(--v2-textarea-focus-ring);
  }

  .v2-base-textarea__meta {
    min-width: 0;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--v2-textarea-meta-gap);
    margin-top: -2px;
  }

  .v2-base-textarea__message,
  .v2-base-textarea__counter {
    margin: 0;
    color: var(--v2-textarea-help-text);
    font-size: var(--v2-textarea-meta-font-size);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-textarea__message {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .v2-base-textarea__counter {
    flex: 0 0 auto;
    margin-left: auto;
    white-space: nowrap;
  }

  .v2-base-textarea--error .v2-base-textarea__native {
    border-color: var(--v2-textarea-border-error);
  }

  .v2-base-textarea--disabled .v2-base-textarea__native {
    color: var(--v2-textarea-disabled-text);
    background: var(--v2-textarea-surface-disabled);
    cursor: not-allowed;
    opacity: var(--v2-textarea-disabled-opacity);
  }

  .v2-base-textarea--readonly .v2-base-textarea__native {
    background: var(--v2-textarea-surface-readonly);
  }
}
</style>
