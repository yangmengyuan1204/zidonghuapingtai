<template>
  <AppModal
    :visible="visible"
    :title="title"
    :submit-label="submitLabel"
    @close="$emit('close')"
    @submit="handleSubmit"
  >
    <template #body>
      <div v-for="field in fields" :key="field.name" class="field">
        <label :for="field.name">{{ field.label }}</label>
        <select
          v-if="field.type === 'select'"
          :id="field.name"
          v-model="form[field.name]"
        >
          <option v-for="opt in field.options || []" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <textarea
          v-else-if="field.type === 'textarea'"
          :id="field.name"
          v-model="form[field.name]"
          :rows="field.rows || 3"
        />
        <input
          v-else
          :id="field.name"
          :type="field.type || 'text'"
          v-model="form[field.name]"
          :placeholder="field.placeholder || ''"
        />
      </div>
    </template>
  </AppModal>
</template>

<script setup>
/**
 * 通用表单弹窗
 * 对齐旧应用 app.js openForm(title, fields, values, onSubmit, submitLabel)
 * fields: [{ name, label, type?, options?, rows?, placeholder?, default? }]
 */
import { ref, watch } from 'vue'
import AppModal from './AppModal.vue'

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
</script>

<style scoped>
/* 使用旧应用 .field / .form-grid 样式（来自 legacy.css） */
</style>
