<template>
  <dialog ref="dialogEl" class="modal" @close="onClose">
    <form v-if="visible" id="modalForm" @submit.prevent="onSubmit">
      <div class="modal-head">
        <h3>{{ title }}</h3>
        <button class="btn secondary" type="button" id="closeModal" @click="close">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <slot name="body">
            <!-- 默认内容，可被 slot 替换 -->
          </slot>
        </div>
      </div>
      <div class="modal-foot">
        <span></span>
        <button class="btn" type="submit">{{ submitLabel }}</button>
      </div>
    </form>
  </dialog>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '' },
  submitLabel: { type: String, default: '保存' },
})

const emit = defineEmits(['close', 'submit'])

const dialogEl = ref(null)

watch(
  () => props.visible,
  (val) => {
    if (val && dialogEl.value && !dialogEl.value.open) {
      dialogEl.value.showModal()
    } else if (!val && dialogEl.value && dialogEl.value.open) {
      dialogEl.value.close()
    }
  }
)

function close() {
  emit('close')
}

function onClose() {
  emit('close')
}

function onSubmit() {
  emit('submit')
}
</script>

<style scoped>
.modal {
  border: none;
  border-radius: 12px;
  padding: 0;
  max-width: 90vw;
  width: 520px;
  box-shadow: var(--v2-modal-shadow, var(--shadow-sm));
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--v2-modal-border, var(--line));
}
.modal-head h3 {
  margin: 0;
  font-size: 16px;
}
.modal-body {
  padding: 20px;
  max-height: 60vh;
  overflow-y: auto;
}
.modal-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-top: 1px solid var(--v2-modal-border, var(--line));
}
</style>
