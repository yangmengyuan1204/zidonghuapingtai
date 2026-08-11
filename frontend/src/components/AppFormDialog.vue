<template>
  <BaseModal
    :open="visible"
    :title="title"
    close-on-backdrop
    @update:open="handleOpenUpdate"
  >
    <form class="v2-app-form-dialog" @submit.prevent="handleSubmit">
      <div class="v2-app-form-dialog__grid">
        <div v-for="field in fields" :key="field.name" class="v2-app-form-dialog__field">
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
  gap: var(--v2-space-3);
}

.v2-app-form-dialog__grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.v2-app-form-dialog__field {
  min-width: 0;
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
