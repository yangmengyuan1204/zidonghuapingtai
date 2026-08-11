<template>
  <AppFormDialog
    :visible="visible"
    :title="title"
    :fields="fields"
    :values="values"
    :submit-label="submitLabel"
    @close="emit('close')"
    @submit="emit('submit', $event)"
  />
</template>

<script setup>
import AppFormDialog from '../AppFormDialog.vue'

defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '' },
  fields: { type: Array, default: () => [] },
  values: { type: Object, default: () => ({}) },
  submitLabel: { type: String, default: '保存' },
})

const emit = defineEmits(['close', 'submit'])
</script>
