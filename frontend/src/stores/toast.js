/**
 * Toast store — 全局提示
 * 对齐旧应用 app.js#L114 的 showToast(message) 行为
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

let timer = null

export const useToastStore = defineStore('toast', () => {
  const message = ref('')
  const visible = ref(false)

  function show(msg) {
    message.value = msg
    visible.value = true
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      visible.value = false
    }, 2600)
  }

  function hide() {
    visible.value = false
    if (timer) clearTimeout(timer)
  }

  return { message, visible, show, hide }
})
