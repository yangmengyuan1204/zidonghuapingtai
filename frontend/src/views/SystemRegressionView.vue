<template>
  <div class="v2-regression">
    <WorkbenchPageHeader
      eyebrow="SYSTEM REGRESSION"
      title="日本站系统回归"
      description="按冻结参数批量验证跨系统业务链路，并集中复查账号前置条件、运行证据和失败恢复。"
    >
      <template #actions>
        <BaseButton variant="secondary" :disabled="busy" @click="loadCases">刷新用例</BaseButton>
        <BaseButton :disabled="busy || !selectedIds.size || !projectId || !envId" @click="startBatch">执行 {{ selectedIds.size }} 个用例</BaseButton>
      </template>
    </WorkbenchPageHeader>

    <div class="v2-regression__context">
      <BaseSelect v-model="projectId" label="项目" :options="projectOptions" @change="onProjectChange" />
      <BaseSelect v-model="envId" label="环境" :options="envOptions" />
      <BaseInput v-model="customerId" label="客户 ID" placeholder="用于回归变量 customer_id" />
      <WorkbenchStatus :tone="batchTone" :label="batchStatusLabel" :detail="batch?.id ? `批次 #${batch.id}` : ''" />
    </div>

    <div class="v2-regression__layout">
      <WorkbenchPanel title="回归用例" :subtitle="`${cases.length} 个用例 · 已选 ${selectedIds.size}`">
        <div class="v2-regression__cases">
          <label v-for="item in cases" :key="item.id" class="v2-regression__case" :class="{ 'v2-regression__case--active': activeCase?.id === item.id }">
            <BaseCheckbox :model-value="selectedIds.has(item.id)" :aria-label="`选择 ${item.name}`" @change="toggleCase(item.id, $event)" />
            <button type="button" @click="activeCase = item">
              <span><strong>{{ item.name }}</strong><small>{{ item.category }} · {{ item.case_key }}</small></span>
              <WorkbenchStatus :tone="item.enabled ? 'success' : 'neutral'" :label="item.enabled ? '启用' : '停用'" compact />
            </button>
          </label>
          <BaseEmptyState v-if="!cases.length" title="没有回归用例" compact icon-hidden />
        </div>
      </WorkbenchPanel>

      <WorkbenchPanel title="用例参数" :subtitle="activeCase ? activeCase.case_key : '选择用例查看参数'">
        <BaseEmptyState v-if="!activeCase" title="选择一个回归用例" icon-hidden />
        <div v-else class="v2-regression__editor">
          <BaseInput v-model="caseDraft.name" label="用例名称" />
          <BaseTextarea v-model="caseParametersText" label="参数（JSON）" :rows="12" :error="caseParametersError" />
          <details class="v2-regression__expectation">
            <summary>预期与身份要求</summary>
            <pre>{{ JSON.stringify(activeCase.expectation || {}, null, 2) }}</pre>
          </details>
          <div class="v2-regression__actions">
            <BaseButton variant="secondary" :disabled="busy" @click="saveCase">保存参数</BaseButton>
            <BaseButton variant="secondary" :disabled="busy" @click="copyActiveCase">复制用例</BaseButton>
            <BaseButton variant="danger" :disabled="busy" @click="resetActiveCase">恢复默认</BaseButton>
          </div>
        </div>
      </WorkbenchPanel>
    </div>

    <WorkbenchPanel v-if="batch" title="批次执行" :subtitle="`批次 #${batch.id}`">
      <template #actions><BaseButton v-if="isBatchRunning" variant="danger" size="compact" @click="stopActiveBatch">停止批次</BaseButton></template>
      <BaseTable :columns="runColumns" :rows="batch.runs || []" row-key="id" :min-content-width="920" aria-label="系统回归执行明细">
        <template #status="{ row }"><WorkbenchStatus :tone="statusTone(row.status)" :label="row.status" compact /></template>
        <template #actions="{ row }">
          <div class="v2-regression__actions">
            <BaseButton variant="secondary" size="compact" @click="rerun(row)">重跑</BaseButton>
            <BaseButton v-if="row.status === 'waiting_account'" size="compact" @click="openAccountResume(row)">补充账号</BaseButton>
          </div>
        </template>
      </BaseTable>
    </WorkbenchPanel>

    <BaseModal :open="accountOpen" title="补充执行账号" @update:open="accountOpen = $event">
      <form class="v2-regression__account-form" @submit.prevent="resumeRunAccount">
        <BaseInput v-model="accountForm.username" label="账号" required />
        <BaseInput v-model="accountForm.password" label="密码" type="password" required />
        <div class="v2-regression__actions"><BaseButton variant="secondary" type="button" @click="accountOpen = false">取消</BaseButton><BaseButton type="submit">恢复执行</BaseButton></div>
      </form>
    </BaseModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import { listEnvs } from '../api/modules/envs.js'
import * as regressionApi from '../api/modules/systemRegression.js'
import { BaseButton, BaseCheckbox, BaseEmptyState, BaseInput, BaseModal, BaseSelect, BaseTable, BaseTextarea } from '../components/v2/base/index.js'
import { WorkbenchPageHeader, WorkbenchPanel, WorkbenchStatus } from '../components/v2/workbench/index.js'

const app = useAppStore()
const toast = useToastStore()
const projects = ref([])
const envs = ref([])
const cases = ref([])
const selectedIds = ref(new Set())
const activeCase = ref(null)
const caseDraft = ref({ name: '' })
const caseParametersText = ref('{}')
const caseParametersError = ref('')
const projectId = ref(localStorage.getItem('systemRegressionProjectId') || app.filters.projectId || '')
const envId = ref(localStorage.getItem('systemRegressionEnvId') || '')
const customerId = ref(localStorage.getItem('systemRegressionCustomerId') || '')
const batch = ref(null)
const busy = ref(false)
const accountOpen = ref(false)
const accountRun = ref(null)
const accountForm = ref({ username: '', password: '' })
let pollTimer = null

const projectOptions = computed(() => [{ value: '', label: '选择项目' }, ...projects.value.map((item) => ({ value: String(item.id), label: item.name }))])
const envOptions = computed(() => [{ value: '', label: '选择环境' }, ...envs.value.map((item) => ({ value: String(item.id), label: item.env_name }))])
const isBatchRunning = computed(() => ['queued', 'running', 'stopping'].includes(batch.value?.status))
const batchTone = computed(() => statusTone(batch.value?.status))
const batchStatusLabel = computed(() => batch.value?.status || '等待执行')
const runColumns = [
  { key: 'id', label: 'ID' }, { key: 'case_key', label: '用例' }, { key: 'status', label: '状态' },
  { key: 'reason_code', label: '结果码' }, { key: 'error_message', label: '结果/错误' }, { key: 'actions', label: '操作' },
]
const statusTone = (status) => ({ passed: 'success', completed: 'success', failed: 'danger', blocked: 'danger', waiting_account: 'warning', running: 'info', queued: 'info', stopped: 'neutral' })[status] || 'neutral'

function toggleCase(id, checked) {
  const next = new Set(selectedIds.value)
  if (checked) next.add(id); else next.delete(id)
  selectedIds.value = next
}

async function loadCases() {
  busy.value = true
  try {
    const response = await regressionApi.listCases()
    cases.value = response.cases || []
    selectedIds.value = new Set(cases.value.filter((item) => item.enabled).map((item) => item.id))
    if (activeCase.value) activeCase.value = cases.value.find((item) => item.id === activeCase.value.id) || null
    if (!activeCase.value && cases.value[0]) activeCase.value = cases.value[0]
  } catch (error) { toast.show(error?.message || '回归用例加载失败') } finally { busy.value = false }
}

async function onProjectChange() {
  localStorage.setItem('systemRegressionProjectId', projectId.value)
  envs.value = projectId.value ? await listEnvs(projectId.value) : []
  if (!envs.value.some((item) => String(item.id) === String(envId.value))) envId.value = envs.value[0] ? String(envs.value[0].id) : ''
}

async function saveCase() {
  caseParametersError.value = ''
  let parameters
  try { parameters = JSON.parse(caseParametersText.value || '{}') } catch { caseParametersError.value = '请输入有效 JSON'; return }
  busy.value = true
  try {
    const updated = await regressionApi.updateCase(activeCase.value.id, { name: caseDraft.value.name, parameters })
    Object.assign(activeCase.value, updated)
    toast.show('用例参数已保存')
  } finally { busy.value = false }
}
async function copyActiveCase() { const copied = await regressionApi.copyCase(activeCase.value.id); cases.value.push(copied); activeCase.value = copied }
async function resetActiveCase() { if (!window.confirm('确认恢复该用例的默认配置吗？')) return; activeCase.value = await regressionApi.resetCase(activeCase.value.id) }

async function startBatch() {
  if (!customerId.value.trim()) return toast.show('请填写客户 ID')
  busy.value = true
  try {
    localStorage.setItem('systemRegressionCustomerId', customerId.value)
    batch.value = await regressionApi.createBatch({ suite_key: 'japan', case_ids: [...selectedIds.value], project_id: Number(projectId.value), env_id: Number(envId.value), context: { variables: { customer_id: customerId.value } } })
    startPolling()
  } catch (error) { toast.show(error?.message || '批次启动失败') } finally { busy.value = false }
}

async function refreshBatch() {
  if (!batch.value?.id) return
  batch.value = await regressionApi.getBatch(batch.value.id)
  if (!isBatchRunning.value) stopPolling()
}
function startPolling() { stopPolling(); pollTimer = window.setInterval(refreshBatch, 1500); refreshBatch() }
function stopPolling() { if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null } }
async function stopActiveBatch() { batch.value = await regressionApi.stopBatch(batch.value.id); stopPolling() }
async function rerun(row) { await regressionApi.rerunCase(row.id); startPolling() }
function openAccountResume(row) { accountRun.value = row; accountForm.value = { username: '', password: '' }; accountOpen.value = true }
async function resumeRunAccount() { await regressionApi.resumeAccount(accountRun.value.id, accountForm.value); accountOpen.value = false; startPolling() }

watch(activeCase, (item) => {
  caseDraft.value = { name: item?.name || '' }
  caseParametersText.value = JSON.stringify(item?.parameters || {}, null, 2)
}, { immediate: true })
watch(envId, (value) => localStorage.setItem('systemRegressionEnvId', value || ''))
onMounted(async () => { projects.value = await app.fetchProjects(); if (!projectId.value && projects.value[0]) projectId.value = String(projects.value[0].id); await Promise.all([onProjectChange(), loadCases()]) })
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.v2-regression {
  display: grid;
  gap: var(--v2-space-3);
  max-width: var(--v2-layout-workspace-max);
  margin: 0 auto;
}

.v2-regression__context {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr)) minmax(220px, .8fr);
  align-items: end;
  gap: var(--v2-space-3);
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-default);
}

.v2-regression__layout {
  display: grid;
  grid-template-columns: minmax(300px, .82fr) minmax(0, 1.6fr);
  align-items: start;
  gap: var(--v2-space-3);
}

.v2-regression__cases {
  display: grid;
  max-height: calc(100vh - var(--v2-space-7) * 4);
  overflow: auto;
}

.v2-regression__case {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  padding: var(--v2-space-2) var(--v2-space-3);
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
}

.v2-regression__case--active,
.v2-regression__case:hover {
  background: var(--v2-action-primary-soft);
}

.v2-regression__case > button {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-2);
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--v2-text-secondary);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.v2-regression__case > button > span {
  display: grid;
  gap: var(--v2-space-micro);
  min-width: 0;
}

.v2-regression__case strong,
.v2-regression__case small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-regression__case small {
  color: var(--v2-text-muted);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
}

.v2-regression__editor,
.v2-regression__account-form {
  display: grid;
  gap: var(--v2-space-3);
  padding: var(--v2-space-3);
}

.v2-regression__expectation {
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-workspace);
}

.v2-regression__expectation summary {
  cursor: pointer;
  color: var(--v2-text-secondary);
  font-weight: var(--v2-font-weight-semibold);
}

.v2-regression__expectation pre {
  max-height: calc(var(--v2-space-7) * 4);
  overflow: auto;
  margin: var(--v2-space-2) 0 0;
  color: var(--v2-text-secondary);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
  white-space: pre-wrap;
}

.v2-regression__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--v2-space-2);
}

@media (max-width: 1080px) {
  .v2-regression__context,
  .v2-regression__layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
