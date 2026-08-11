<template>
  <div class="v2-requirement">
    <WorkbenchPageHeader
      eyebrow="REQUIREMENT INTELLIGENCE"
      title="需求验证中心"
      description="把需求材料转成可确认的验证项，并通过预检、执行和人工确认形成证据闭环。"
    >
      <template #actions>
        <BaseSelect v-model="projectId" aria-label="筛选需求项目" :options="projectOptions" @change="loadTasks" />
        <BaseButton v-if="auth.isAdmin" @click="createOpen = true">新建验证任务</BaseButton>
      </template>
    </WorkbenchPageHeader>

    <BaseErrorState v-if="errorMessage" title="需求验证中心加载失败" :message="errorMessage" action-label="重新加载" @action="loadTasks" />

    <div v-else class="v2-requirement__layout">
      <WorkbenchPanel title="验证任务" :subtitle="`${tasks.length} 个任务`">
        <div class="v2-requirement__filter">
          <BaseInput v-model="keyword" aria-label="搜索验证任务" placeholder="按需求名称搜索" @keyup.enter="loadTasks" />
          <BaseButton variant="secondary" @click="loadTasks">搜索</BaseButton>
        </div>
        <div class="v2-requirement__tasks">
          <button
            v-for="task in tasks"
            :key="task.id"
            class="v2-requirement__task"
            :class="{ 'v2-requirement__task--active': task.id === selectedId }"
            type="button"
            @click="selectTask(task.id)"
          >
            <span><strong>{{ task.name }}</strong><small>{{ task.update_time || task.create_time }}</small></span>
            <WorkbenchStatus :tone="statusTone(task.latest_result || task.status)" :label="task.latest_result || task.status" compact />
          </button>
          <BaseEmptyState v-if="!tasks.length" title="暂无验证任务" compact icon-hidden />
        </div>
      </WorkbenchPanel>

      <WorkbenchPanel title="任务工作区" :subtitle="detail ? `任务 #${detail.id} · 分析版本 ${detail.analysis_version || 0}` : '选择左侧任务查看详情'">
        <BaseEmptyState v-if="!detail" title="选择一个验证任务" description="详情、验证项和执行状态会显示在这里。" icon-hidden />
        <div v-else class="v2-requirement__detail">
          <div class="v2-requirement__detail-head">
            <div><h2>{{ detail.name }}</h2><p>{{ detail.requirement_text || '暂无需求正文' }}</p></div>
            <WorkbenchStatus :tone="statusTone(detail.status)" :label="detail.status" />
          </div>

          <div class="v2-requirement__metrics">
            <div><span>验证项</span><strong>{{ detail.items?.length || 0 }}</strong></div>
            <div><span>澄清项</span><strong>{{ detail.clarifications?.length || 0 }}</strong></div>
            <div><span>材料</span><strong>{{ detail.materials?.length || 0 }}</strong></div>
            <div><span>执行记录</span><strong>{{ detail.runs?.length || 0 }}</strong></div>
          </div>

          <div class="v2-requirement__actions">
            <BaseButton v-if="auth.isAdmin" variant="secondary" :disabled="busy" @click="analyze">生成验证计划</BaseButton>
            <BaseButton v-if="auth.isAdmin" :disabled="busy || !(detail.items?.length)" @click="startRun">预检并执行</BaseButton>
            <BaseButton v-if="auth.isAdmin" variant="danger" :disabled="busy" @click="removeTask">删除任务</BaseButton>
          </div>

          <div class="v2-requirement__items">
            <article v-for="item in detail.items || []" :key="item.id" class="v2-requirement__item">
              <div><strong>{{ item.title }}</strong><p>{{ item.expected || item.action_goal || item.precondition }}</p></div>
              <WorkbenchStatus :tone="statusTone(item.status)" :label="item.status" compact />
            </article>
            <BaseEmptyState v-if="!(detail.items || []).length" title="尚未生成验证项" description="点击“生成验证计划”开始分析。" compact icon-hidden />
          </div>

          <section v-if="activeRun" class="v2-requirement__run">
            <div><WorkbenchStatus :tone="statusTone(activeRun.status)" :label="activeRun.status" /><span>运行 #{{ activeRun.id }}</span></div>
            <div class="v2-requirement__actions">
              <BaseButton variant="secondary" @click="refreshRun">刷新</BaseButton>
              <BaseButton v-if="activeRun.status === 'running'" variant="secondary" @click="pauseActiveRun">暂停</BaseButton>
              <BaseButton v-if="activeRun.status === 'paused'" @click="resumeActiveRun">继续</BaseButton>
              <BaseButton variant="danger" @click="cancelActiveRun">取消</BaseButton>
            </div>
          </section>
        </div>
      </WorkbenchPanel>
    </div>

    <BaseModal :open="createOpen" title="新建需求验证任务" @update:open="createOpen = $event">
      <form class="v2-requirement__form" @submit.prevent="createVerificationTask">
        <BaseSelect v-model="createForm.project_id" label="项目" :options="projectOptions.filter((item) => item.value)" required />
        <BaseInput v-model="createForm.name" label="需求名称" required />
        <BaseInput v-model="createForm.target_url" label="目标页面 URL" />
        <BaseTextarea v-model="createForm.requirement_text" label="需求说明" :rows="9" required />
        <div class="v2-requirement__actions"><BaseButton variant="secondary" type="button" @click="createOpen = false">取消</BaseButton><BaseButton type="submit" :disabled="busy">创建任务</BaseButton></div>
      </form>
    </BaseModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import * as verificationApi from '../api/modules/requirementVerification.js'
import { BaseButton, BaseEmptyState, BaseErrorState, BaseInput, BaseModal, BaseSelect, BaseTextarea } from '../components/v2/base/index.js'
import { WorkbenchPageHeader, WorkbenchPanel, WorkbenchStatus } from '../components/v2/workbench/index.js'

const auth = useAuthStore()
const app = useAppStore()
const toast = useToastStore()
const projects = ref([])
const projectId = ref(app.filters.projectId || '')
const keyword = ref('')
const tasks = ref([])
const selectedId = ref(null)
const detail = ref(null)
const activeRun = ref(null)
const errorMessage = ref('')
const busy = ref(false)
const createOpen = ref(false)
const createForm = ref({ project_id: '', name: '', target_url: '', requirement_text: '' })
let runTimer = null

const projectOptions = computed(() => [{ value: '', label: '全部项目' }, ...projects.value.map((item) => ({ value: String(item.id), label: item.name }))])
const statusTone = (status) => ({ passed: 'success', completed: 'success', failed: 'danger', blocked: 'danger', running: 'info', paused: 'warning', pending: 'warning', plan_generated: 'info' })[String(status || '').toLowerCase()] || 'neutral'

async function loadTasks() {
  errorMessage.value = ''
  try {
    tasks.value = await verificationApi.listTasks({ projectId: projectId.value, keyword: keyword.value })
    if (selectedId.value && !tasks.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = null
      detail.value = null
    }
  } catch (error) { errorMessage.value = error?.message || '请稍后重试' }
}

async function selectTask(id) {
  selectedId.value = id
  detail.value = await verificationApi.getTask(id)
}

async function createVerificationTask() {
  busy.value = true
  try {
    const created = await verificationApi.createTask({ ...createForm.value, project_id: Number(createForm.value.project_id), target_pages: [], data_setup: {}, context: '' })
    createOpen.value = false
    createForm.value = { project_id: projectId.value, name: '', target_url: '', requirement_text: '' }
    await loadTasks()
    await selectTask(created.id)
  } catch (error) { toast.show(error?.message || '创建失败') } finally { busy.value = false }
}

async function analyze() {
  busy.value = true
  try { detail.value = await verificationApi.analyzeTask(detail.value.id) } catch (error) { toast.show(error?.message || '分析失败') } finally { busy.value = false }
}

async function startRun() {
  busy.value = true
  try {
    const itemIds = (detail.value.items || []).map((item) => item.id)
    const payload = { item_ids: itemIds, variables: {}, data_setup: detail.value.data_setup || null, runtime_check: true, visible_browser: true }
    await verificationApi.preflightTask(detail.value.id, payload)
    activeRun.value = await verificationApi.runTask(detail.value.id, { item_ids: itemIds, variables: {}, data_setup: detail.value.data_setup || null, risk_confirmed: true, visible_browser: true, mode: 'quick', dataset_overrides: {} })
    startRunPolling()
  } catch (error) { toast.show(error?.message || '执行启动失败') } finally { busy.value = false }
}

async function refreshRun() {
  if (!activeRun.value?.id) return
  activeRun.value = await verificationApi.getRun(activeRun.value.id)
  if (['completed', 'failed', 'cancelled'].includes(activeRun.value.status)) stopRunPolling()
}
function startRunPolling() { stopRunPolling(); runTimer = window.setInterval(refreshRun, 1500); refreshRun() }
function stopRunPolling() { if (runTimer) { window.clearInterval(runTimer); runTimer = null } }
async function pauseActiveRun() { activeRun.value = await verificationApi.pauseRun(activeRun.value.id); stopRunPolling() }
async function resumeActiveRun() { activeRun.value = await verificationApi.resumeRun(activeRun.value.id); startRunPolling() }
async function cancelActiveRun() { activeRun.value = await verificationApi.cancelRun(activeRun.value.id); stopRunPolling() }

async function removeTask() {
  if (!window.confirm(`确认删除“${detail.value.name}”吗？`)) return
  await verificationApi.deleteTask(detail.value.id)
  selectedId.value = null
  detail.value = null
  await loadTasks()
}

onMounted(async () => {
  projects.value = await app.fetchProjects()
  createForm.value.project_id = projectId.value || (projects.value[0] ? String(projects.value[0].id) : '')
  await loadTasks()
})
onBeforeUnmount(stopRunPolling)
</script>

<style scoped>
.v2-requirement {
  display: grid;
  gap: var(--v2-space-3);
  max-width: var(--v2-layout-workspace-max);
  margin: 0 auto;
}

.v2-requirement__layout {
  display: grid;
  grid-template-columns: minmax(280px, .72fr) minmax(0, 1.8fr);
  gap: var(--v2-space-3);
  align-items: start;
}

.v2-requirement__filter,
.v2-requirement__actions,
.v2-requirement__detail-head,
.v2-requirement__run,
.v2-requirement__run > div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--v2-space-2);
}

.v2-requirement__filter {
  padding: var(--v2-space-3);
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
}

.v2-requirement__tasks {
  display: grid;
}

.v2-requirement__task {
  display: flex;
  min-height: var(--v2-size-table-row);
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-2);
  padding: var(--v2-space-2) var(--v2-space-3);
  border: 0;
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
  background: var(--v2-surface-default);
  color: var(--v2-text-secondary);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.v2-requirement__task--active,
.v2-requirement__task:hover {
  background: var(--v2-action-primary-soft);
}

.v2-requirement__task > span {
  display: grid;
  gap: var(--v2-space-micro);
  min-width: 0;
}

.v2-requirement__task strong,
.v2-requirement__task small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-requirement__task small,
.v2-requirement__detail-head p,
.v2-requirement__item p {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
}

.v2-requirement__detail {
  display: grid;
  gap: var(--v2-space-3);
  padding: var(--v2-space-3);
}

.v2-requirement__detail-head,
.v2-requirement__run {
  justify-content: space-between;
}

.v2-requirement__detail-head h2,
.v2-requirement__detail-head p,
.v2-requirement__item p {
  margin: 0;
}

.v2-requirement__detail-head h2 {
  font-size: var(--v2-font-size-section);
}

.v2-requirement__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--v2-space-2);
}

.v2-requirement__metrics div {
  display: grid;
  gap: var(--v2-space-micro);
  padding: var(--v2-space-2);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-workspace);
}

.v2-requirement__metrics span {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
}

.v2-requirement__items,
.v2-requirement__form {
  display: grid;
  gap: var(--v2-space-2);
}

.v2-requirement__item,
.v2-requirement__run {
  display: flex;
  justify-content: space-between;
  gap: var(--v2-space-3);
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-workspace);
}

.v2-requirement__actions {
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .v2-requirement__layout,
  .v2-requirement__metrics {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
