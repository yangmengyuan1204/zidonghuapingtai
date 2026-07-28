<template>
  <!-- 对齐旧应用 renderApiCases()：工具栏 + 表格 + 分页 -->
  <div class="toolbar">
    <div class="filters">
      <div class="field compact">
        <label>项目</label>
        <select :value="filterProjectId" @change="onProjectChange">
          <option value="">全部</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </div>
      <div class="field compact">
        <label>环境</label>
        <select :value="filterEnvId" @change="onEnvChange">
          <option value="">全部</option>
          <option v-for="e in envs" :key="e.id" :value="String(e.id)">{{ e.env_name }}</option>
        </select>
      </div>
    </div>
    <div class="actions">
      <button class="btn secondary" :disabled="selectedIds.size === 0" @click="openBatchRun">批量执行 {{ selectedIds.size || '' }}</button>
      <button v-if="auth.isAdmin" class="btn" @click="openForm(null)">新增接口用例</button>
    </div>
  </div>

  <AppTable :columns="columns" :rows="rows">
    <!-- 选择框列（对齐旧应用 select 列） -->
    <template #select="{ row }">
      <input
        type="checkbox"
        :checked="selectedIds.has(row.id)"
        @change="toggleSelect(row.id, $event)"
      />
    </template>
    <template #project_id="{ row }">{{ projectName(row.project_id) }}</template>
    <template #env_id="{ row }">{{ envName(row.env_id) }}</template>
    <template #method="{ row }">
      <span class="badge" :class="badgeClass(row.method)">{{ badgeText(row.method) }}</span>
    </template>
    <template #status="{ row }">
      <span class="badge" :class="apiCaseStatusClass(row.status)">{{ apiCaseStatusText(row.status) }}</span>
    </template>
    <template #actions="{ row }">
      <div class="actions">
        <button class="btn" @click="onRun(row)">执行</button>
        <template v-if="auth.isAdmin">
          <button class="btn secondary" @click="onCopy(row)">复制</button>
          <button class="btn secondary" @click="openForm(row)">编辑</button>
          <button class="btn danger" @click="onDelete(row)">删除</button>
        </template>
      </div>
    </template>
  </AppTable>

  <!-- 分页：对齐旧应用 renderApiCases 分页结构 -->
  <div class="pagination">
    <span class="page-info">共 {{ total }} 条，第 {{ page }}/{{ totalPages }} 页</span>
    <div class="page-buttons">
      <button class="btn secondary" :disabled="page <= 1" @click="goPage('prev')">上一页</button>
      <template v-for="(btn, idx) in pageButtons" :key="idx">
        <span v-if="btn === '...'" class="page-ellipsis">...</span>
        <button
          v-else
          :class="['btn', Number(btn) === page ? 'active' : 'secondary']"
          @click="goPage(Number(btn))"
        >{{ btn }}</button>
      </template>
      <button class="btn secondary" :disabled="page >= totalPages" @click="goPage('next')">下一页</button>
    </div>
  </div>

  <!-- 新增/编辑/复制表单弹窗 -->
  <AppFormDialog
    :visible="formVisible"
    :title="formTitle"
    :fields="formFields"
    :values="formValues"
    @close="closeForm"
    @submit="submitForm"
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
 * - 单条执行：runApiCase → POST /execute → 跳转 /records
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
import AppTable from '../components/AppTable.vue'
import AppFormDialog from '../components/AppFormDialog.vue'
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
async function onRun(item) {
  try {
    toast.show('正在执行，请稍候')
    const body = {}
    if (filterEnvId.value) body.env_id = Number(filterEnvId.value)
    const record = await apiCasesApi.executeApiCase(item.id, body)
    toast.show(`执行完成：${record.result === 'passed' ? '成功' : '失败'}`)
    // 对齐旧应用 state.view = 'records'; await renderShell();
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
/* 使用旧应用 .toolbar / .filters / .field / .actions / .badge / .pagination 样式（来自 styles.css） */
</style>
