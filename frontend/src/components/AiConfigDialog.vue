<template>
  <BaseModal
    :open="open"
    title="全局 AI 配置"
    description="修改后会影响全平台后续启动的 AI 任务。"
    @update:open="emit('update:open', $event)"
  >
    <form id="globalAiConfigForm" class="ai-config-dialog__form" @submit.prevent="saveConfig">
      <BaseSelect
        v-model="form.provider"
        label="服务类型"
        :options="providerOptions"
        :disabled="loading || saving"
      />
      <BaseInput
        v-model="form.base_url"
        label="API 地址"
        required
        :disabled="loading || saving"
      />
      <BaseInput
        v-model="form.model"
        label="模型名称"
        required
        :disabled="loading || saving"
      />
      <BaseInput
        v-model="form.api_key"
        label="API Key"
        type="password"
        autocomplete="new-password"
        placeholder="留空则保留现有密钥"
        :disabled="loading || saving"
      />
      <p class="ai-config-dialog__hint">当前模型：{{ currentModel || '未配置' }}</p>
      <p v-if="statusMessage" class="ai-config-dialog__status" aria-live="polite">{{ statusMessage }}</p>
    </form>

    <template #footer>
      <BaseButton variant="secondary" type="button" :disabled="loading || testing || saving" @click="testConnection">
        {{ testing ? '正在测试...' : '测试连接' }}
      </BaseButton>
      <BaseButton type="submit" form="globalAiConfigForm" :disabled="loading || testing || saving">
        {{ saving ? '正在保存...' : '保存配置' }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api/client.js'
import { useToastStore } from '../stores/toast.js'
import { BaseButton, BaseInput, BaseModal, BaseSelect } from './v2/base/index.js'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['update:open'])
const toast = useToastStore()
const providerOptions = [
  { value: 'openai_compatible', label: 'OpenAI 兼容' },
  { value: 'ollama', label: 'Ollama' },
]
const form = reactive({
  provider: 'openai_compatible',
  base_url: '',
  model: '',
  api_key: '',
})
const currentModel = ref('')
const statusMessage = ref('')
const loading = ref(false)
const testing = ref(false)
const saving = ref(false)

function payload() {
  return {
    provider: String(form.provider || 'openai_compatible').trim(),
    base_url: String(form.base_url || '').trim(),
    model: String(form.model || '').trim(),
    api_key: String(form.api_key || '').trim(),
  }
}

async function loadConfig() {
  loading.value = true
  statusMessage.value = ''
  try {
    const config = await api('/api/ai-config')
    form.provider = config.provider || 'openai_compatible'
    form.base_url = config.base_url || ''
    form.model = config.model || ''
    form.api_key = ''
    currentModel.value = config.model || ''
  } finally {
    loading.value = false
  }
}

async function testConnection() {
  testing.value = true
  statusMessage.value = ''
  try {
    const result = await api('/api/ai-config/test', { method: 'POST', body: payload() })
    statusMessage.value = `${result.message}，模型：${result.model}`
  } catch (error) {
    statusMessage.value = error.message || '连接测试失败'
  } finally {
    testing.value = false
  }
}

async function saveConfig() {
  saving.value = true
  statusMessage.value = ''
  try {
    const saved = await api('/api/ai-config', { method: 'PUT', body: payload() })
    currentModel.value = saved.model || ''
    toast.show('全局 AI 配置已保存')
    emit('update:open', false)
  } finally {
    saving.value = false
  }
}

watch(() => props.open, (open) => {
  if (open) loadConfig()
})
</script>

<style scoped>
.ai-config-dialog__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 16px;
  padding: 4px 0;
}

.ai-config-dialog__form :deep(.v2-base-input),
.ai-config-dialog__form :deep(.v2-base-select) {
  min-width: 0;
  --v2-input-height: 36px;
  --v2-select-height: 36px;
  --v2-input-radius: 7px;
  --v2-select-radius: 7px;
}

.ai-config-dialog__form :deep(.v2-base-input__label),
.ai-config-dialog__form :deep(.v2-base-select__label) {
  margin-bottom: 5px;
  color: var(--v2-text-muted);
  font-size: 11px;
  font-weight: 500;
}

.ai-config-dialog__hint,
.ai-config-dialog__status {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--v2-text-muted);
  font-size: 12px;
}

.ai-config-dialog__hint {
  padding: 10px 12px;
  border: 1px solid var(--v2-border-panel);
  border-radius: 8px;
  background: var(--v2-surface-workspace);
}

.ai-config-dialog__status {
  color: var(--v2-text-primary);
}

@media (max-width: 640px) {
  .ai-config-dialog__form {
    grid-template-columns: 1fr;
  }
}
</style>
