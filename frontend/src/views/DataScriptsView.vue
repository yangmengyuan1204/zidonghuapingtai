<template>
  <div class="v2-data-scripts">
    <WorkbenchPageHeader
      eyebrow="DATA AUTOMATION"
      title="数据工厂"
      description="从受控脚本目录运行数据任务，或让智能体先生成计划、确认风险后执行。"
    >
      <template #actions>
        <BaseSelect v-model="projectId" aria-label="数据工厂项目" :options="projectOptions" @change="onProjectChange" />
        <BaseSelect v-model="envId" aria-label="数据工厂环境" :options="envOptions" />
      </template>
    </WorkbenchPageHeader>

    <div class="v2-data-scripts__tabs" role="tablist" aria-label="数据工厂模式">
      <BaseButton :variant="activeTab === 'scripts' ? 'primary' : 'secondary'" role="tab" :aria-selected="activeTab === 'scripts'" @click="setTab('scripts')">脚本执行</BaseButton>
      <BaseButton :variant="activeTab === 'agent' ? 'primary' : 'secondary'" role="tab" :aria-selected="activeTab === 'agent'" @click="setTab('agent')">智能体任务</BaseButton>
    </div>

    <BaseErrorState v-if="pageError" title="数据工厂加载失败" :message="pageError" action-label="重新加载" @action="loadWorkspace" />

    <div v-else-if="activeTab === 'scripts'" class="v2-data-scripts__layout">
      <WorkbenchPanel title="脚本目录" :subtitle="`${catalog.length} 个当前项目可用脚本`">
        <DataScriptCatalog :items="catalog" :selected="selectedType" @select="selectedType = $event" />
      </WorkbenchPanel>
      <WorkbenchPanel title="运行控制台" subtitle="沿用 project_id / env_id / variables 请求合同">
        <DataScriptRunner
          :script="selectedScript"
          :variables-text="variablesText"
          :running="running"
          :result="resultText"
          :error="variablesError"
          @update:variables-text="updateVariables"
          @run="runSelectedScript"
        />
      </WorkbenchPanel>
    </div>

    <WorkbenchPanel v-else title="数据智能体" subtitle="目标理解 → 计划确认 → 风险确认 → 执行验证">
      <DataAgentWorkspace
        :session="agentSession"
        :instruction="agentInstruction"
        :busy="agentBusy"
        @update:instruction="agentInstruction = $event"
        @create="createAgent"
        @refresh="refreshAgent"
        @confirm="confirmAgent"
        @cancel="cancelAgent"
      />
    </WorkbenchPanel>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import { listEnvs } from '../api/modules/envs.js'
import * as dataScriptsApi from '../api/modules/dataScripts.js'
import DataAgentWorkspace from '../components/data-scripts/DataAgentWorkspace.vue'
import DataScriptCatalog from '../components/data-scripts/DataScriptCatalog.vue'
import DataScriptRunner from '../components/data-scripts/DataScriptRunner.vue'
import { BaseButton, BaseErrorState, BaseSelect } from '../components/v2/base/index.js'
import { WorkbenchPageHeader, WorkbenchPanel } from '../components/v2/workbench/index.js'

const auth = useAuthStore()
const app = useAppStore()
const toast = useToastStore()
const projects = ref([])
const envs = ref([])
const catalog = ref([])
const projectId = ref(localStorage.getItem('factoryProjectId') || app.filters.projectId || '')
const envId = ref(localStorage.getItem('factoryEnvId') || '')
const activeTab = ref(localStorage.getItem('dataScriptTab') === 'agent' ? 'agent' : 'scripts')
const selectedType = ref('')
const variablesText = ref(localStorage.getItem('factoryVariables') || '{}')
const variablesError = ref('')
const running = ref(false)
const resultText = ref('')
const pageError = ref('')
const agentInstruction = ref('')
const agentSession = ref(null)
const agentBusy = ref(false)

const projectOptions = computed(() => [{ value: '', label: '选择项目' }, ...projects.value.map((item) => ({ value: String(item.id), label: item.name }))])
const envOptions = computed(() => [{ value: '', label: '选择环境' }, ...envs.value.map((item) => ({ value: String(item.id), label: item.env_name }))])
const selectedScript = computed(() => catalog.value.find((item) => item.script_type === selectedType.value) || null)

function setTab(tab) {
  activeTab.value = tab
  localStorage.setItem('dataScriptTab', tab)
}

function updateVariables(value) {
  variablesText.value = value
  localStorage.setItem('factoryVariables', value)
}

async function loadProjectContext() {
  if (!projectId.value) {
    envs.value = []
    catalog.value = []
    return
  }
  const [envList, scriptList] = await Promise.all([listEnvs(projectId.value), dataScriptsApi.listDataScriptCatalog(projectId.value)])
  envs.value = envList
  catalog.value = scriptList
  if (!catalog.value.some((item) => item.script_type === selectedType.value)) selectedType.value = catalog.value[0]?.script_type || ''
  if (!envs.value.some((item) => String(item.id) === String(envId.value))) envId.value = envs.value[0] ? String(envs.value[0].id) : ''
}

async function loadWorkspace() {
  pageError.value = ''
  try {
    projects.value = await app.fetchProjects()
    if (!projectId.value && projects.value[0]) projectId.value = String(projects.value[0].id)
    await loadProjectContext()
  } catch (error) {
    pageError.value = error?.message || '请稍后重试'
  }
}

async function onProjectChange() {
  localStorage.setItem('factoryProjectId', projectId.value)
  app.setProjectId(projectId.value)
  await loadProjectContext()
}

async function runSelectedScript() {
  variablesError.value = ''
  let variables
  try {
    variables = JSON.parse(variablesText.value || '{}')
  } catch {
    variablesError.value = '请输入有效 JSON'
    return
  }
  if (!selectedScript.value || !projectId.value || !envId.value) {
    variablesError.value = '请先选择项目、环境和脚本'
    return
  }
  if (selectedScript.value.risk_level === 'high' && !window.confirm('该脚本会改变业务状态，确认继续执行吗？')) return
  running.value = true
  try {
    const result = await dataScriptsApi.executeDataScript(selectedType.value, { project_id: Number(projectId.value), env_id: Number(envId.value), variables })
    resultText.value = JSON.stringify(result, null, 2)
    toast.show('数据脚本执行完成')
  } catch (error) {
    variablesError.value = error?.message || '执行失败'
  } finally {
    running.value = false
  }
}

async function createAgent() {
  if (!auth.isAdmin) return toast.show('仅管理员可以启动数据智能体')
  if (!projectId.value || !envId.value || !agentInstruction.value.trim()) return toast.show('请填写项目、环境和任务说明')
  agentBusy.value = true
  try {
    const customerIds = String(localStorage.getItem('dataScriptCustomerIds') || '').split(/[\n,，;；]+/).map((item) => item.trim()).filter(Boolean)
    agentSession.value = await dataScriptsApi.createAgentSession({ project_id: Number(projectId.value), env_id: Number(envId.value), instruction: agentInstruction.value.trim(), topbar_customer_ids: customerIds })
  } catch (error) {
    toast.show(error?.message || '智能体任务创建失败')
  } finally {
    agentBusy.value = false
  }
}

async function refreshAgent() {
  if (!agentSession.value?.id) return
  agentBusy.value = true
  try { agentSession.value = await dataScriptsApi.getAgentSession(agentSession.value.id) } finally { agentBusy.value = false }
}

async function confirmAgent() {
  if (!agentSession.value?.id) return
  agentBusy.value = true
  try {
    if (agentSession.value.status === 'waiting_risk_confirmation' && agentSession.value.contract_hash) {
      agentSession.value = await dataScriptsApi.confirmAgentRisk(agentSession.value.id, { plan_version: agentSession.value.plan_version, contract_hash: agentSession.value.contract_hash, acknowledged: true })
    } else {
      agentSession.value = await dataScriptsApi.confirmAgentSession(agentSession.value.id, agentSession.value.plan_version)
    }
  } catch (error) {
    toast.show(error?.message || '确认失败')
  } finally {
    agentBusy.value = false
  }
}

async function cancelAgent() {
  if (!agentSession.value?.id) return
  agentBusy.value = true
  try { agentSession.value = await dataScriptsApi.cancelAgentSession(agentSession.value.id) } finally { agentBusy.value = false }
}

watch(envId, (value) => localStorage.setItem('factoryEnvId', value || ''))
onMounted(loadWorkspace)
</script>

<style scoped>
.v2-data-scripts {
  display: grid;
  gap: var(--v2-space-3);
  max-width: var(--v2-layout-workspace-max);
  margin: 0 auto;
}

.v2-data-scripts__tabs {
  display: flex;
  gap: var(--v2-space-2);
}

.v2-data-scripts__layout {
  display: grid;
  grid-template-columns: minmax(260px, .72fr) minmax(0, 1.7fr);
  gap: var(--v2-space-3);
  align-items: start;
}

@media (max-width: 900px) {
  .v2-data-scripts__layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
