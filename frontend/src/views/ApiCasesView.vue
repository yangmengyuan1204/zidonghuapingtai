<template>
  <!-- 对齐旧应用 renderApiCases()：工具栏 + 表格 + 分页 -->
  <div class="v2-api-cases">
  <WorkbenchPageHeader
    eyebrow="TEST ASSETS"
    title="接口用例库"
    description="按项目与环境管理接口测试资产，支持选择、批量执行和单条调试。"
  >
    <template #actions>
      <BaseButton
        v-if="auth.isAdmin"
        type="button"
        variant="primary"
        @click="openForm(null)"
      >新增接口用例</BaseButton>
    </template>
  </WorkbenchPageHeader>
  <WorkbenchPanel title="接口用例" subtitle="筛选条件与选择状态在执行前保持不变">
  <div class="v2-api-cases-content">
  <section class="v2-api-cases-section v2-api-cases-section--toolbar" aria-label="筛选与批量操作">
  <div class="v2-api-cases-toolbar">
    <div class="v2-api-cases-filters">
      <div class="v2-api-cases-filter">
        <BaseSelect
          label="项目"
          placeholder="全部"
          :model-value="filterProjectId"
          :options="projects"
          option-value="id"
          option-label="name"
          @change="onProjectChange"
        />
      </div>
      <div class="v2-api-cases-filter">
        <BaseSelect
          label="环境"
          placeholder="全部"
          :model-value="filterEnvId"
          :options="envs"
          option-value="id"
          option-label="env_name"
          @change="onEnvChange"
        />
      </div>
    </div>
    <div class="v2-api-cases-actions">
      <BaseButton
        v-if="auth.isAdmin"
        type="button"
        variant="secondary"
        :disabled="selectedIds.size === 0"
        @click="openBatchRun"
      >批量执行 {{ selectedIds.size || '' }}</BaseButton>
    </div>
  </div>
  </section>

  <section class="v2-api-cases-section v2-api-cases-section--table" aria-label="用例列表">
  <BaseTable
    :columns="columns"
    :rows="rows"
    row-key="id"
    aria-label="接口用例列表"
    :loading="loading"
    :min-content-width="986"
  >
    <!-- 选择框列（对齐旧应用 select 列） -->
    <template #select="{ row }">
      <BaseCheckbox
        :model-value="selectedIds.has(row.id)"
        :aria-label="`选择接口用例 ${row.case_name || row.id}`"
        @change="toggleSelect(row.id, $event)"
      />
    </template>
    <template #id="{ row }">{{ shortText(row.id) }}</template>
    <template #project_id="{ row }">{{ projectName(row.project_id) }}</template>
    <template #env_id="{ row }">{{ envName(row.env_id) }}</template>
    <template #case_name="{ row }">{{ shortText(row.case_name) }}</template>
    <template #method="{ row }">
      <BaseBadge tone="neutral" size="compact">{{ badgeText(row.method) }}</BaseBadge>
    </template>
    <template #url="{ row }">{{ shortText(row.url) }}</template>
    <template #status="{ row }">
      <BaseBadge :tone="apiCaseStatusTone(row.status)" size="compact">{{ apiCaseStatusText(row.status) }}</BaseBadge>
    </template>
    <template #actions="{ row }">
      <div class="v2-api-cases-row-actions">
        <BaseButton v-if="auth.isAdmin" type="button" variant="primary" size="compact" @click="onRun(row)">执行</BaseButton>
        <template v-if="auth.isAdmin">
          <BaseButton type="button" variant="secondary" size="compact" @click="onCopy(row)">复制</BaseButton>
          <BaseButton type="button" variant="secondary" size="compact" @click="openForm(row)">编辑</BaseButton>
          <BaseButton type="button" variant="danger" size="compact" @click="onDelete(row)">删除</BaseButton>
        </template>
      </div>
    </template>
  </BaseTable>
  </section>

  <!-- 分页：对齐旧应用 renderApiCases 分页结构 -->
  <footer class="v2-api-cases-section v2-api-cases-section--footer">
  <div class="v2-api-cases-pagination">
    <span class="v2-api-cases-page-info">共 {{ total }} 条，第 {{ page }}/{{ totalPages }} 页</span>
    <BasePagination
      :page="page"
      :total="total"
      :page-size="pageSize"
      :sibling-count="2"
      aria-label="接口用例分页"
      @change="goPage"
    />
  </div>
  </footer>
  </div>
  </WorkbenchPanel>

  <!-- 新增/编辑/复制表单弹窗 -->
  <AppFormDialog
    :visible="formVisible"
    :title="formTitle"
    :fields="formFields"
    :values="formValues"
    @close="closeForm"
    @submit="submitForm"
  />

  <!-- 单条执行参数弹窗 -->
  <AppFormDialog
    :visible="runVisible"
    title="执行接口用例"
    :fields="runFields"
    :values="runValues"
    submit-label="执行"
    @close="closeRun"
    @submit="submitRun"
  />

  <!-- 批量执行弹窗 -->
  <AppFormDialog
    :visible="batchVisible"
    title="批量执行"
    :fields="batchFields"
    :values="{}"
    submit-label="执行"
    @close="closeBatch"
    @submit="submitBatch"
  />
  </div>
</template>

<script setup>
/**
 * ApiCases 视图 — 迁移自旧应用 renderApiCases()
 *
 * 对齐项：
 * - 列表：columns（select/ID/项目/环境/用例名称/方法/URL/状态/操作）
 * - 筛选：项目筛选 + 环境筛选（环境跟随项目联动）
 * - 分页：上一页/下一页 + 页码按钮 + 首尾省略号
 * - CRUD：新增/编辑/复制/删除（admin）
 * - 单条执行：打开参数弹窗 → POST /execute → 跳转 /records
 * - 批量执行：openBatchApiRun → 选择用例 → variables → 跳转 /records
 * - 选择：checkbox + state.selectedApiIds
 * - 权限：admin 可见增删改按钮，normal 不可见
 * - 状态 Badge：apiCaseStatusBadge（active=ok / inactive=warn）
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import AppFormDialog from '../components/AppFormDialog.vue'
import { WorkbenchPageHeader, WorkbenchPanel } from '../components/v2/workbench/index.js'
import {
  BaseBadge,
  BaseButton,
  BaseCheckbox,
  BasePagination,
  BaseSelect,
  BaseTable,
} from '../components/v2/base/index.js'
import { badgeText, badgeClass } from '../utils/badge.js'
import * as apiCasesApi from '../api/modules/apiCases.js'
import { listEnvs } from '../api/modules/envs.js'

const router = useRouter()
const auth = useAuthStore()
const appStore = useAppStore()
const toast = useToastStore()

// ========== 状态 ==========
const projects = ref([])
const allEnvs = ref([])
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const filterProjectId = ref(appStore.filters.projectId || '')
const filterEnvId = ref(appStore.filters.envId || '')
const selectedIds = ref(new Set())

// ========== 列定义 ==========
const columns = [
  { key: 'select', label: '', slot: 'select' },
  { key: 'id', label: 'ID' },
  { key: 'project_id', label: '项目', slot: 'project_id' },
  { key: 'env_id', label: '环境', slot: 'env_id' },
  { key: 'case_name', label: '用例名称' },
  { key: 'method', label: '方法', slot: 'method' },
  { key: 'url', label: 'URL' },
  { key: 'status', label: '状态', slot: 'status' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

// ========== 计算 ==========
// 环境列表：根据项目筛选联动（对齐旧应用）
const envs = computed(() => {
  if (!filterProjectId.value) return allEnvs.value
  return allEnvs.value.filter((e) => String(e.project_id) === String(filterProjectId.value))
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const pageButtons = computed(() => {
  const btns = []
  const start = Math.max(1, page.value - 2)
  const end = Math.min(totalPages.value, page.value + 2)
  if (start > 1) {
    btns.push('1')
    if (start > 2) btns.push('...')
  }
  for (let i = start; i <= end; i++) {
    btns.push(String(i))
  }
  if (end < totalPages.value) {
    if (end < totalPages.value - 1) btns.push('...')
    btns.push(String(totalPages.value))
  }
  return btns
})

// ========== 名称映射 ==========
function projectName(id) {
  const p = projects.value.find((item) => item.id === id)
  return p ? p.name : id
}

function envName(id) {
  const e = allEnvs.value.find((item) => item.id === id)
  return e ? e.env_name : id
}

// ========== 状态 Badge（对齐旧应用 apiCaseStatusBadge） ==========
function apiCaseStatusText(value) {
  const labels = { active: '启用', inactive: '停用', disabled: '停用' }
  return labels[value] || badgeText(value)
}

function apiCaseStatusClass(value) {
  if (value === 'active') return 'ok'
  if (value === 'inactive' || value === 'disabled') return 'warn'
  return badgeClass(value)
}

function apiCaseStatusTone(value) {
  return {
    ok: 'success',
    fail: 'danger',
    warn: 'warning',
  }[apiCaseStatusClass(value)] || 'neutral'
}

function shortText(value, length = 140) {
  const s = String(value ?? '')
  return s.length > length ? s.slice(0, length) + '...' : s
}

// ========== 数据加载 ==========
async function loadApiCases() {
  loading.value = true
  try {
    const resp = await apiCasesApi.listApiCases({
      projectId: filterProjectId.value,
      envId: filterEnvId.value,
      page: page.value,
      pageSize,
    })
    rows.value = resp.items || []
    total.value = resp.total ?? rows.value.length
    const tp = Math.max(1, Math.ceil(total.value / pageSize))
    if (page.value > tp) {
      page.value = tp
      await loadApiCases()
    }
  } catch (error) {
    toast.show(error.message)
  } finally {
    loading.value = false
  }
}

// ========== 筛选切换 ==========
async function onProjectChange(event) {
  filterProjectId.value = event.target.value
  // 对齐旧应用：项目切换时清空环境筛选 + 页码重置 + 清空选择
  filterEnvId.value = ''
  appStore.filters.envId = ''
  page.value = 1
  appStore.setProjectId(filterProjectId.value)
  selectedIds.value = new Set()
  await loadApiCases()
}

async function onEnvChange(event) {
  filterEnvId.value = event.target.value
  appStore.filters.envId = filterEnvId.value
  page.value = 1
  selectedIds.value = new Set()
  await loadApiCases()
}

// ========== 分页 ==========
async function goPage(target) {
  if (target === 'prev') {
    page.value = Math.max(1, page.value - 1)
  } else if (target === 'next') {
    page.value = Math.min(totalPages.value, page.value + 1)
  } else {
    page.value = Number(target)
  }
  await loadApiCases()
}

// ========== 选择 ==========
function toggleSelect(id, event) {
  const next = new Set(selectedIds.value)
  if (event.target.checked) next.add(id)
  else next.delete(id)
  selectedIds.value = next
}

// ========== 表单（新增/编辑/复制） ==========
const formVisible = ref(false)
const formTitle = ref('')
const formValues = ref({})
const editingItem = ref(null)
const forceCreate = ref(false)

// 项目/环境选项（对齐旧应用 projectOptions / envOptions）
const projectOptions = computed(() =>
  projects.value.map((item) => ({ value: item.id, label: item.name })),
)

const envOptions = computed(() =>
  allEnvs.value.map((item) => ({
    value: item.id,
    label: `${item.env_name} (${projectName(item.project_id)})`,
  })),
)

const methodOptions = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((item) => ({
  value: item,
  label: item,
}))

const statusOptions = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '停用' },
]

const formFields = computed(() => [
  { name: 'project_id', label: '项目', type: 'select', options: projectOptions.value, required: true },
  { name: 'env_id', label: '环境', type: 'select', options: envOptions.value, required: true },
  { name: 'case_name', label: '用例名称', required: true },
  { name: 'method', label: '请求方法', type: 'select', options: methodOptions, required: true },
  { name: 'url', label: 'URL', required: true },
  { name: 'headers', label: '请求头 JSON', type: 'textarea', default: '{}' },
  { name: 'params', label: '参数 JSON', type: 'textarea', default: '{}' },
  { name: 'body', label: '请求体', type: 'textarea' },
  { name: 'assert_rule', label: '断言/提取 JSON', type: 'textarea', default: '{"status_code":200,"extract":{"id":"json.data.id"}}' },
  { name: 'status', label: '状态', type: 'select', options: statusOptions, default: 'active' },
])

function openForm(item) {
  editingItem.value = item
  forceCreate.value = false
  formTitle.value = item ? '编辑接口用例' : '新增接口用例'
  formValues.value = item ? { ...item } : {}
  formVisible.value = true
}

function onCopy(item) {
  // 对齐旧应用 apiCaseForm({...item, id: undefined, case_name: `${item.case_name}_copy`}, ..., true)
  editingItem.value = { ...item, id: undefined, case_name: `${item.case_name}_copy` }
  forceCreate.value = true
  formTitle.value = '新增接口用例'
  formValues.value = { ...editingItem.value }
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingItem.value = null
  forceCreate.value = false
}

async function submitForm(data) {
  try {
    const isUpdate = editingItem.value && editingItem.value.id && !forceCreate.value
    if (isUpdate) {
      await apiCasesApi.updateApiCase(editingItem.value.id, data)
    } else {
      await apiCasesApi.createApiCase(data)
    }
    toast.show('已保存')
    closeForm()
    await loadApiCases()
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 删除 ==========
async function onDelete(item) {
  if (!confirm('确认删除这条数据？')) return
  try {
    await apiCasesApi.deleteApiCase(item.id)
    toast.show('已删除')
    await loadApiCases()
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 单条执行 ==========
const runVisible = ref(false)
const runningItem = ref(null)
const runValues = ref({})
const runFields = computed(() => [
  {
    name: 'env_id',
    label: '执行环境',
    type: 'select',
    options: allEnvs.value
      .filter((env) => String(env.project_id) === String(runningItem.value?.project_id))
      .map((env) => ({ value: env.id, label: env.env_name })),
    required: true,
  },
  { name: 'variables', label: '运行时变量 JSON', type: 'textarea', rows: 8, default: '{}' },
])

function onRun(item) {
  runningItem.value = item
  runValues.value = {
    env_id: filterEnvId.value || item.env_id || '',
    variables: '{}',
  }
  runVisible.value = true
}

function closeRun() {
  runVisible.value = false
  runningItem.value = null
}

async function submitRun(data) {
  try {
    toast.show('正在执行，请稍候')
    const payload = {
      env_id: Number(data.env_id),
      variables: parseJsonObject(data.variables),
    }
    const record = await apiCasesApi.executeApiCase(runningItem.value.id, payload)
    toast.show(`执行完成：${record.result === 'passed' ? '成功' : '失败'}`)
    closeRun()
    router.push('/records')
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 批量执行 ==========
const batchVisible = ref(false)
const batchFields = [
  {
    name: 'variables',
    label: '运行时变量 JSON',
    type: 'textarea',
    rows: 8,
    default: '{\n  "username": "test_{{$random_int}}",\n  "phone": "{{$random_phone}}"\n}',
  },
]

function openBatchRun() {
  const ids = [...selectedIds.value]
  if (!ids.length) {
    toast.show('请选择接口用例')
    return
  }
  batchVisible.value = true
}

function closeBatch() {
  batchVisible.value = false
}

async function submitBatch(data) {
  try {
    const caseIds = [...selectedIds.value]
    const payload = {
      case_ids: caseIds,
      variables: parseJsonText(data.variables, {}),
    }
    if (filterEnvId.value) payload.env_id = Number(filterEnvId.value)
    const result = await apiCasesApi.batchExecuteApiCases(payload)
    selectedIds.value = new Set()
    toast.show(`批量执行完成：${result.records.length} 条`)
    closeBatch()
    router.push('/records')
  } catch (error) {
    toast.show(error.message)
  }
}

// 对齐旧应用 parseJsonText
function parseJsonText(text, fallback) {
  if (!text) return fallback
  try {
    return JSON.parse(text)
  } catch {
    return fallback
  }
}

function parseJsonObject(text) {
  try {
    const value = JSON.parse(text || '{}')
    if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error()
    return value
  } catch {
    throw new Error('运行时变量必须是有效的 JSON 对象')
  }
}

// ========== 生命周期 ==========
onMounted(async () => {
  if (!auth.user) {
    await auth.fetchMe()
  }
  // 加载项目 + 所有环境（对齐旧应用 Promise.all([getProjects(), api('/api/envs')])）
  const [projectList, envList] = await Promise.all([
    appStore.fetchProjects(),
    listEnvs(),
  ])
  projects.value = projectList
  allEnvs.value = envList
  appStore.setProjects(projectList)

  // 对齐旧应用：环境筛选若不在当前项目环境列表中则清空
  if (filterEnvId.value && !envs.value.some((e) => String(e.id) === String(filterEnvId.value))) {
    filterEnvId.value = ''
  }

  await loadApiCases()
})
</script>

<style scoped>
.v2-api-cases {
  display: grid;
  gap: 0;
  width: 100%;
  max-width: none;
  margin: 0;
}

.v2-api-cases :deep(.v2-workbench-page-header) {
  min-height: auto;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.v2-api-cases :deep(.v2-workbench-page-header::before) {
  background: transparent;
}

.v2-api-cases :deep(.v2-workbench-page-header__eyebrow) {
  margin-bottom: 6px;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
}

.v2-api-cases :deep(.v2-workbench-page-header__title) {
  color: var(--v2-shell-pilot-text-heading);
  font-size: 26px;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.v2-api-cases :deep(.v2-workbench-page-header__description) {
  margin-top: 3px;
  color: var(--v2-shell-pilot-text-muted);
  font-size: 13px;
  line-height: 20px;
}

.v2-api-cases :deep(.v2-workbench-page-header__actions) {
  gap: 8px;
}

.v2-api-cases :deep(.v2-workbench-page-header__actions .v2-base-button--primary) {
  --v2-button-height: 36px;
  --v2-button-radius: 7px;
  --v2-button-padding: 14px;
  --v2-button-font-size: 13px;
  --v2-button-font-weight: 500;
  --v2-button-bg: var(--v2-shell-pilot-primary);
  --v2-button-bg-hover: var(--v2-shell-pilot-primary-hover);
  --v2-button-bg-pressed: var(--v2-shell-pilot-primary-hover);
}

.v2-api-cases :deep(.v2-workbench-panel) {
  gap: 10px;
}

.v2-api-cases :deep(.v2-workbench-panel__header) {
  min-height: 0;
  padding: 0 2px;
  border: 0;
  background: transparent;
}

.v2-api-cases :deep(.v2-workbench-panel__title) {
  color: var(--v2-shell-pilot-text-body);
  font-size: 13px;
  font-weight: 600;
}

.v2-api-cases :deep(.v2-workbench-panel__subtitle) {
  color: var(--v2-shell-pilot-text-faint);
  font-size: 12px;
}

.v2-api-cases :deep(.v2-workbench-panel__body) {
  display: flex;
  min-height: calc(100vh - 180px);
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
}

.v2-api-cases-content {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
}

.v2-api-cases-section--toolbar {
  flex: 0 0 auto;
}

.v2-api-cases-section--table {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
}

.v2-api-cases-section--footer {
  flex: 0 0 auto;
}

.v2-api-cases-toolbar {
  min-height: 64px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--v2-shell-pilot-card-border);
  background: #ffffff;
}

.v2-api-cases-filters,
.v2-api-cases-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.v2-api-cases-actions {
  align-items: center;
}

.v2-api-cases-filter {
  min-width: 160px;
  max-width: 220px;
}

.v2-api-cases-filter :deep(.v2-base-select__label) {
  margin-bottom: 5px;
  color: var(--v2-shell-pilot-text-muted);
  font-size: 11px;
  font-weight: 500;
}

.v2-api-cases-filter :deep(.v2-base-select) {
  --v2-select-height: 36px;
  --v2-select-radius: 7px;
  --v2-select-border: var(--v2-color-field-border);
  --v2-select-border-hover: var(--v2-color-border-slate);
  --v2-select-border-focus: var(--v2-border-focus);
  --v2-select-font-size: 13px;
  --v2-select-focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.14);
}

.v2-api-cases-toolbar :deep(.v2-base-button--secondary) {
  --v2-button-height: 36px;
  --v2-button-radius: 7px;
  --v2-button-padding: 13px;
  --v2-button-font-size: 13px;
  --v2-button-font-weight: 500;
  --v2-button-secondary-bg: #ffffff;
  --v2-button-secondary-border: var(--v2-color-field-border);
  --v2-button-secondary-text: var(--v2-shell-pilot-text-body);
  --v2-button-secondary-bg-hover: #ffffff;
  --v2-button-secondary-bg-pressed: #ffffff;
}

.v2-api-cases-toolbar :deep(.v2-base-button--secondary:disabled) {
  background: transparent;
  border-color: var(--v2-shell-pilot-card-border);
  color: var(--v2-color-text-disabled-neutral);
  opacity: 1;
  cursor: not-allowed;
}

.v2-api-cases :deep(.v2-base-table) {
  flex: 1 1 auto;
  border: 0;
  border-radius: 0;
  background: #ffffff;
}

.v2-api-cases :deep(.v2-base-table__table) {
  min-width: 900px;
  table-layout: fixed;
  font-variant-numeric: tabular-nums;
}

.v2-api-cases :deep(.v2-base-table__header),
.v2-api-cases :deep(.v2-base-table__cell) {
  padding-right: 12px;
  padding-left: 12px;
  padding-top: 0;
  padding-bottom: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-api-cases :deep(.v2-base-table__header) {
  height: 40px;
  background: var(--v2-color-surface-hover-neutral);
  color: var(--v2-shell-pilot-text-muted);
  border-bottom: 1px solid var(--v2-shell-pilot-card-border);
  font-size: 11px;
  font-weight: 600;
}

.v2-api-cases :deep(.v2-base-table__cell) {
  height: 44px;
  background: #ffffff;
  color: var(--v2-shell-pilot-text-body);
  border-bottom: 1px solid var(--v2-color-row-border);
  font-size: 13px;
}

.v2-api-cases :deep(.v2-base-table__row:hover .v2-base-table__cell) {
  background: var(--v2-color-surface-hover-neutral);
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(1)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(1)) {
  width: 44px;
  padding-right: 8px;
  padding-left: 14px;
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(2)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(2)) {
  width: 86px;
  color: var(--v2-shell-pilot-text-muted);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(3)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(3)) {
  width: 116px;
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(4)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(4)) {
  width: 136px;
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(5)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(5)) {
  width: 180px;
  color: var(--v2-shell-pilot-text-heading);
  font-weight: 500;
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(6)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(6)) {
  width: 84px;
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(7)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(7)) {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  color: var(--v2-shell-pilot-text-secondary);
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(8)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(8)) {
  width: 92px;
}

.v2-api-cases :deep(.v2-base-table__header:nth-child(9)),
.v2-api-cases :deep(.v2-base-table__cell:nth-child(9)) {
  width: 226px;
  padding-right: 12px;
  padding-left: 4px;
}

.v2-api-cases :deep(.v2-base-checkbox) {
  --v2-checkbox-size: 14px;
  --v2-checkbox-selected-surface: var(--v2-shell-pilot-primary);
  --v2-checkbox-focus-ring: 0 0 0 3px rgba(93, 135, 255, 0.16);
}

.v2-api-cases :deep(.v2-base-table__cell:nth-child(6)) .v2-base-badge {
  height: 22px;
  padding: 0 7px;
  border-radius: 5px;
  background: var(--v2-color-surface-soft-neutral);
  color: var(--v2-shell-pilot-text-secondary);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
  font-weight: 600;
}

.v2-api-cases :deep(.v2-base-table__cell:nth-child(8)) .v2-base-badge--success {
  height: 22px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--v2-color-success-bg);
  color: var(--v2-color-success-text);
  font-size: 10px;
  font-weight: 600;
}

.v2-api-cases :deep(.v2-base-table__cell:nth-child(8)) .v2-base-badge--warning {
  height: 22px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--v2-color-warning-bg);
  color: var(--v2-color-warning-text);
  font-size: 10px;
  font-weight: 600;
}

.v2-api-cases-row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.v2-api-cases-row-actions :deep(.v2-base-button--compact) {
  --v2-button-height: 30px;
  --v2-button-font-size: 12px;
  --v2-button-font-weight: 500;
}

.v2-api-cases-row-actions :deep(.v2-base-button--primary) {
  --v2-button-radius: 6px;
  --v2-button-padding: 10px;
  --v2-button-bg: var(--v2-shell-pilot-primary);
  --v2-button-bg-hover: var(--v2-shell-pilot-primary-hover);
  --v2-button-bg-pressed: var(--v2-shell-pilot-primary-hover);
}

.v2-api-cases-row-actions :deep(.v2-base-button--secondary) {
  --v2-button-radius: 6px;
  --v2-button-padding: 8px;
  --v2-button-secondary-bg: transparent;
  --v2-button-secondary-border: transparent;
  --v2-button-secondary-text: var(--v2-shell-pilot-text-secondary);
  --v2-button-secondary-bg-hover: var(--v2-color-surface-soft-neutral);
  --v2-button-secondary-bg-pressed: var(--v2-color-surface-soft-neutral);
}

.v2-api-cases-row-actions :deep(.v2-base-button--danger) {
  --v2-button-radius: 6px;
  --v2-button-padding: 8px;
  --v2-button-danger-bg: transparent;
  --v2-button-danger-border: transparent;
  --v2-button-danger-text: var(--v2-color-danger-base);
  --v2-button-danger-bg-hover: var(--v2-color-danger-bg);
  --v2-button-danger-bg-pressed: var(--v2-color-danger-bg);
}

.v2-api-cases-row-actions :deep(.v2-base-button--danger:hover:not(:disabled)) {
  color: var(--v2-color-danger-text);
}

.v2-api-cases-pagination {
  min-height: 56px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 16px;
  border-top: var(--v2-border-width) solid var(--v2-shell-pilot-card-border);
  background: #ffffff;
}

.v2-api-cases-page-info {
  margin-right: auto;
  color: var(--v2-shell-pilot-text-faint);
  font-size: 12px;
  white-space: nowrap;
}

.v2-api-cases :deep(.v2-base-pagination) {
  --v2-pagination-control-size: 30px;
  --v2-pagination-radius: 6px;
  --v2-pagination-font-size: 12px;
  --v2-pagination-gap: 4px;
  --v2-pagination-surface-active: var(--v2-color-brand-blue-soft);
  --v2-pagination-text-active: var(--v2-color-brand-blue-active);
  --v2-pagination-surface-hover: var(--v2-color-surface-hover-neutral);
  --v2-pagination-text-hover: var(--v2-color-brand-blue-active);
  --v2-pagination-border-hover: var(--v2-color-brand-blue-focus);
  --v2-pagination-font-weight: 500;
}

.v2-api-cases :deep(.v2-base-table__state-cell) {
  padding: 56px 20px;
  color: var(--v2-shell-pilot-text-faint);
  border-bottom: 0;
}

.v2-api-cases :deep(.v2-base-empty-state) {
  min-height: 180px;
  justify-content: center;
}

.v2-api-cases :deep(.v2-base-empty-state__icon) {
  width: 56px;
  height: 56px;
  color: #94a3b8;
  background: #f1f5f9;
}

@media (max-width: 720px) {
  .v2-api-cases-toolbar,
  .v2-api-cases-pagination {
    align-items: stretch;
    flex-direction: column;
  }

  .v2-api-cases-actions {
    justify-content: flex-end;
  }

  .v2-api-cases-page-info {
    margin-right: 0;
  }
}
</style>
