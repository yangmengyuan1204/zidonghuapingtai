<template>
  <dialog ref="dialogEl" class="modal" @close="emit('close')">
    <form v-if="visible" @submit.prevent="submit">
      <div class="modal-head">
        <h3>录制UI用例</h3>
        <button class="btn secondary" type="button" @click="emit('close')">取消</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>项目</label>
            <select v-model="form.project_id" required @change="loadConfig">
              <option value="" disabled>请选择项目</option>
              <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
            </select>
          </div>
          <div class="field">
            <label>用例名称</label>
            <input v-model="form.case_name" required placeholder="例如：创建订单主流程" />
          </div>
          <div class="field">
            <label>起始URL</label>
            <input v-model="form.start_url" required type="url" placeholder="https://…" />
          </div>
          <div class="field">
            <label>测试账号（首次登录后自动保存登录态）</label>
            <select v-model="form.account_profile_id">
              <option value="">不复用登录态</option>
              <option v-for="acc in accounts" :key="acc.id" :value="String(acc.id)">{{ acc.name || acc.username || acc.id }}</option>
            </select>
          </div>
          <div class="field">
            <label>数据重置脚本</label>
            <select v-model="form.reset_script_key" required :disabled="!form.project_id">
              <option value="" disabled>请选择数据重置脚本</option>
              <option v-for="script in scripts" :key="script.script_type" :value="script.script_type">{{ script.name }}</option>
            </select>
          </div>
          <div class="field">
            <label>数据重置环境</label>
            <select v-model="form.reset_env_id" required :disabled="!form.project_id">
              <option value="" disabled>请选择环境</option>
              <option v-for="env in envs" :key="env.id" :value="String(env.id)">{{ env.name }}</option>
            </select>
          </div>
          <div class="field">
            <label>重置参数（JSON，不含密码/Token）</label>
            <textarea v-model="form.reset_variables" rows="4" placeholder='{"customer_id": 1001}'></textarea>
            <p v-if="resetError" class="v2-ui-record-start__error">{{ resetError }}</p>
          </div>
        </div>
      </div>
      <div class="modal-foot">
        <span>保存项目配置后启动可视化录制浏览器</span>
        <button class="btn" type="submit" :disabled="saving">{{ saving ? '保存配置中…' : '开始录制' }}</button>
      </div>
    </form>
  </dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useToastStore } from '../../stores/toast.js'
import { getUiRecordProjectConfig, saveUiRecordProjectConfig } from '../../api/modules/uiCases.js'
import { listEnvs } from '../../api/modules/envs.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projects: { type: Array, default: () => [] },
  accounts: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'start'])
const toast = useToastStore()
const dialogEl = ref(null)
const saving = ref(false)
const scripts = ref([])
const envs = ref([])
const resetError = ref('')
const form = reactive({
  project_id: '',
  case_name: '',
  start_url: '',
  account_profile_id: '',
  reset_script_key: '',
  reset_env_id: '',
  reset_variables: '{}',
})

const SENSITIVE_KEY_PARTS = ['password', 'token', 'cookie', 'secret', 'authorization']

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      form.project_id = String(props.projects[0]?.id || '')
      loadConfig()
      if (dialogEl.value && !dialogEl.value.open) dialogEl.value.showModal()
    } else if (dialogEl.value?.open) {
      dialogEl.value.close()
    }
  },
)

async function loadConfig() {
  resetError.value = ''
  if (!form.project_id) return
  const projectId = Number(form.project_id)
  try {
    const [configData, envData] = await Promise.all([getUiRecordProjectConfig(projectId), listEnvs(projectId)])
    scripts.value = configData?.available_scripts || []
    envs.value = envData?.items || envData || []
    const config = configData?.config
    if (config) {
      form.reset_script_key = config.reset_script_key || ''
      form.reset_env_id = config.reset_env_id ? String(config.reset_env_id) : ''
      form.reset_variables = config.reset_variables ? JSON.stringify(config.reset_variables, null, 2) : '{}'
    }
  } catch (error) {
    toast.show(error.message || '加载项目录制配置失败')
  }
}

function containsSensitiveKey(value) {
  if (Array.isArray(value)) return value.some(containsSensitiveKey)
  if (value && typeof value === 'object') {
    return Object.keys(value).some((key) => {
      const lower = String(key).toLowerCase()
      return SENSITIVE_KEY_PARTS.some((part) => lower.includes(part)) || containsSensitiveKey(value[key])
    })
  }
  return false
}

function parseResetVariables() {
  resetError.value = ''
  if (!form.reset_variables.trim()) return {}
  try {
    const value = JSON.parse(form.reset_variables)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('重置参数必须是 JSON 对象')
    if (containsSensitiveKey(value)) {
      resetError.value = '重置参数不能包含密码、Token 或 Cookie'
      return null
    }
    return value
  } catch (error) {
    resetError.value = `重置参数 JSON 无效：${error.message}`
    return null
  }
}

async function submit() {
  if (!form.case_name.trim() || !form.start_url.trim()) return
  if (!form.reset_script_key || !form.reset_env_id) {
    toast.show('请选择数据重置脚本和环境')
    return
  }
  const resetVariables = parseResetVariables()
  if (resetVariables === null) return
  saving.value = true
  try {
    await saveUiRecordProjectConfig(Number(form.project_id), {
      reset_script_key: form.reset_script_key,
      reset_env_id: Number(form.reset_env_id),
      reset_variables: resetVariables,
    })
    emit('start', {
      project_id: Number(form.project_id),
      case_name: form.case_name.trim(),
      start_url: form.start_url.trim(),
      account_profile_id: form.account_profile_id ? Number(form.account_profile_id) : '',
    })
  } catch (error) {
    toast.show(error.message || '保存项目配置失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.v2-ui-record-start__error {
  margin: var(--v2-space-1) 0 0;
  color: var(--v2-color-danger, #dc2626);
  font-size: var(--v2-font-size-caption);
}
</style>