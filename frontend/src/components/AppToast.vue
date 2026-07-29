<template>
  <!-- 使用全局 .toast（design-system-base.css），与旧应用同一风格 -->
  <div v-if="toast.visible" class="toast">
    {{ toast.message }}
  </div>
</template>

<script setup>
import { useToastStore } from '../stores/toast.js'
const toast = useToastStore()
</script>
