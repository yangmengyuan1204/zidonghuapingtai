<template>
  <div v-if="toast.visible" class="toast" :class="{ 'toast-show': toast.visible }">
    {{ toast.message }}
  </div>
</template>

<script setup>
import { useToastStore } from '../stores/toast.js'
const toast = useToastStore()
</script>

<style scoped>
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--nav-solid, #1e293b);
  color: #fff;
  padding: 10px 20px;
  border-radius: 8px;
  z-index: 9999;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 14px;
  transition: opacity 0.2s;
}
</style>
