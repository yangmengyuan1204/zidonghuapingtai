<template>
  <BaseModal
    :open="visible"
    :title="title"
    close-on-backdrop
    @update:open="handleOpenUpdate"
  >
    <form class="v2-app-form-dialog" @submit.prevent="handleSubmit">
      <div class="v2-app-form-dialog__grid">
        <div
          v-for="field in fields"
          :key="field.name"
          class="v2-app-form-dialog__field"
          :class="{ 'v2-app-form-dialog__field--full': field.type === 'textarea' }"
        >
          <BaseSelect
            v-if="field.type === 'select'"
            :id="field.name"
            v-model="form[field.name]"
            :name="field.name"
            :label="field.label"
            :options="field.options || []"
            :required="Boolean(field.required)"
            :disabled="Boolean(field.disabled)"
            :error="field.error || ''"
            :help="field.help || ''"
          />
        <BaseTextarea
          v-else-if="field.type === 'textarea'"
          :id="field.name"
          v-model="form[field.name]"
          :name="field.name"
          :label="field.label"
          :rows="field.rows || 3"
          :maxlength="field.maxlength"
          :required="Boolean(field.required)"
          :disabled="Boolean(field.disabled)"
          :readonly="Boolean(field.readonly)"
          :placeholder="field.placeholder || ''"
          :error="field.error || ''"
          :help="field.help || ''"
        />
          <BaseInput
          v-else
          :id="field.name"
          v-model="form[field.name]"
          :name="field.name"
          :type="field.type || 'text'"
          :label="field.label"
          :placeholder="field.placeholder || ''"
          :required="Boolean(field.required)"
          :disabled="Boolean(field.disabled)"
          :readonly="Boolean(field.readonly)"
          :error="field.error || ''"
          :help="field.help || ''"
        />
      </div>
      </div>
      <div class="v2-app-form-dialog__actions">
        <BaseButton type="button" variant="secondary" @click="$emit('close')">取消</BaseButton>
        <BaseButton type="submit">{{ submitLabel }}</BaseButton>
      </div>
    </form>
  </BaseModal>
</template>

<script setup>
/**
 * 通用表单弹窗
 * 对齐旧应用 app.js openForm(title, fields, values, onSubmit, submitLabel)
 * fields: [{ name, label, type?, options?, rows?, placeholder?, default? }]
 */
import { ref, watch } from 'vue'
import { BaseButton, BaseInput, BaseModal, BaseSelect, BaseTextarea } from './v2/base/index.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '' },
  fields: { type: Array, default: () => [] },
  values: { type: Object, default: () => ({}) },
  submitLabel: { type: String, default: '保存' },
})

const emit = defineEmits(['close', 'submit'])

const form = ref({})

watch(
  () => props.visible,
  (val) => {
    if (val) {
      // 初始化表单值
      const obj = {}
      for (const field of props.fields) {
        obj[field.name] = props.values?.[field.name] ?? field.default ?? ''
      }
      form.value = obj
    }
  },
  { immediate: true }
)

function handleSubmit() {
  emit('submit', { ...form.value })
}

function handleOpenUpdate(open) {
  if (!open) emit('close')
}
</script>

<style scoped>
.v2-app-form-dialog,
.v2-app-form-dialog__grid {
  display: grid;
  gap: 16px;
}

.v2-app-form-dialog__grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.v2-app-form-dialog__field {
  min-width: 0;
}

.v2-app-form-dialog :deep(.v2-base-input__label),
.v2-app-form-dialog :deep(.v2-base-select__label),
.v2-app-form-dialog :deep(.v2-base-textarea__label) {
  margin-bottom: 6px;
  color: var(--v2-shell-pilot-text-body);
  font-size: 12px;
  font-weight: 500;
}

.v2-app-form-dialog :deep(.v2-base-input),
.v2-app-form-dialog :deep(.v2-base-select),
.v2-app-form-dialog :deep(.v2-base-textarea) {
  /* White modal surface: use light field chrome, never sidebar white/alpha borders */
  --v2-input-border: var(--v2-color-field-border);
  --v2-input-border-hover: var(--v2-color-border-slate);
  --v2-input-border-focus: var(--v2-border-focus);
  --v2-input-focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.14);
  --v2-select-border: var(--v2-color-field-border);
  --v2-select-border-hover: var(--v2-color-border-slate);
  --v2-select-border-focus: var(--v2-border-focus);
  --v2-select-focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.14);
  --v2-textarea-border: var(--v2-color-field-border);
  --v2-textarea-border-hover: var(--v2-color-border-slate);
  --v2-textarea-border-focus: var(--v2-border-focus);
  --v2-textarea-focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.14);
}

.v2-app-form-dialog :deep(.v2-base-input__control),
.v2-app-form-dialog :deep(.v2-base-select__native) {
  height: var(--v2-control-height-default);
  min-height: var(--v2-control-height-default);
  border-radius: var(--v2-radius-sm);
}

.v2-app-form-dialog :deep(.v2-base-input__native),
.v2-app-form-dialog :deep(.v2-base-select__native) {
  font-size: 13px;
}

.v2-app-form-dialog :deep(.v2-base-textarea__native) {
  min-height: 120px;
  padding: 10px 12px;
  border-radius: var(--v2-radius-sm);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.6;
}

.v2-app-form-dialog__field--full {
  grid-column: 1 / -1;
}

.v2-app-form-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--v2-space-2);
  padding-top: var(--v2-space-3);
  border-top: var(--v2-border-width) solid var(--v2-border-panel);
}

@media (max-width: 640px) {
  .v2-app-form-dialog__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
