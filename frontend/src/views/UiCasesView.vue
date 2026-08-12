<template>
  <!-- 对齐旧应用 renderUiCases()：工具栏 + 表格（无分页/无搜索/无环境筛选） -->
  <div class="v2-ui-cases">
  <WorkbenchPageHeader
    eyebrow="BROWSER AUTOMATION"
    title="UI 自动化"
    description="管理浏览器用例、录制真实操作，并在可视化执行中追踪步骤、截图和事件。"
  />
  <WorkbenchPanel title="UI 用例" subtitle="业务会话、轮询与卸载清理逻辑保持在页面编排层">
  <div class="toolbar">
    <div class="filters">
      <div class="field compact">
        <label>项目</label>
        <select :value="filterProjectId" @change="onProjectChange">
          <option value="">全部</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </div>
    </div>
    <div class="actions">
      <button v-if="auth.isAdmin" class="btn" @click="openRecordStartDialog">录制UI用例</button>
      <button v-if="auth.isAdmin" class="btn secondary" @click="openForm(null)">新增UI用例</button>
    </div>
  </div>

  <AppTable :columns="columns" :rows="rows">
    <template #project_id="{ row }">{{ projectName(row.project_id) }}</template>
    <template #account_profile_name="{ row }">{{ row.account_profile_name || '跟随项目' }}</template>
    <template #status="{ row }">
      <span class="badge" :class="badgeClass(row.status)">{{ badgeText(row.status) }}</span>
    </template>
    <template #actions="{ row }">
      <div class="actions">
        <button class="btn" @click="onRun(row)">执行</button>
        <template v-if="auth.isAdmin">
          <button class="btn secondary" @click="openForm(row)">编辑</button>
          <button class="btn danger" @click="onDelete(row)">删除</button>
        </template>
      </div>
    </template>
  </AppTable>
  </WorkbenchPanel>

  <!-- 新增/编辑表单弹窗（对齐旧应用 uiCaseForm → openForm） -->
  <UiCaseForm
    :visible="formVisible"
    :title="formTitle"
    :fields="formFields"
    :values="formValues"
    @close="closeForm"
    @submit="submitForm"
  />

  <!-- 录制UI用例-启动表单弹窗（对齐旧应用 openUiRecordStartDialog → openForm） -->
  <AppFormDialog
    :visible="recordStartVisible"
    title="录制UI用例"
    :fields="recordStartFields"
    :values="recordStartValues"
    submit-label="开始录制"
    @close="closeRecordStart"
    @submit="submitRecordStart"
  />

  <!-- 录制中弹窗（对齐旧应用 renderUiRecordSessionDialog） -->
  <dialog ref="recordDialogEl" class="modal" @close="onRecordDialogClose">
    <div v-if="recordVisible">
      <div class="modal-head">
        <h3>录制UI用例：{{ recordSession.case_name || '' }}</h3>
        <button class="btn secondary" type="button" @click="cancelRecordSession">取消</button>
      </div>
      <div class="modal-body">
        <UiRecordingPanel
          :session="recordSession"
          :rows="recordPreviewRows"
          @cancel="cancelRecordSession"
          @save="openRecordSaveDialog"
        />
      </div>
    </div>
  </dialog>

  <!-- 录制-保存弹窗（对齐旧应用 openUiRecordSaveDialog） -->
  <dialog ref="recordSaveDialogEl" class="modal" @close="onRecordSaveDialogClose">
    <form v-if="recordSaveVisible" @submit.prevent="submitRecordSave">
      <div class="modal-head">
        <h3>保存录制用例</h3>
        <button class="btn secondary" type="button" @click="backToRecord">返回录制</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>用例名称</label>
            <input :value="recordSession.case_name || ''" disabled />
          </div>
          <div class="field">
            <label>已捕获事件</label>
            <input :value="recordSession.count || 0" disabled />
          </div>
          <div class="field">
            <label>最终URL</label>
            <input :value="recordSession.current_url || recordSession.start_url || ''" disabled />
          </div>
          <div class="field">
            <label>页面文案断言（可选）</label>
            <input v-model="recordSaveForm.assertion_text" placeholder="例如：保存成功、登录成功" />
          </div>
        </div>
        <div class="panel table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th><th>步骤</th><th>动作</th><th>定位器</th><th>值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(step, idx) in recordPreviewRows" :key="idx">
                <td>{{ idx + 1 }}</td>
                <td>{{ step.name || step.action || '-' }}</td>
                <td><span class="badge">{{ step.action || '-' }}</span></td>
                <td>{{ recordShort(step.locator) }}</td>
                <td>{{ recordShort(step.value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="modal-foot">
        <span>保存后会生成草稿 UI 用例，可直接点执行复跑</span>
        <button class="btn" type="submit" :disabled="recordSaving">{{ recordSaving ? '保存中...' : '保存用例' }}</button>
      </div>
    </form>
  </dialog>

  <!-- 可视化执行表单弹窗（对齐旧应用 openUiExecuteForm，自定义布局） -->
  <dialog ref="executeDialogEl" class="modal" @close="onExecuteDialogClose">
    <form v-if="executeVisible" @submit.prevent="submitExecuteForm">
      <div class="modal-head">
        <h3>执行 {{ executeItem?.case_name || '' }}</h3>
        <button class="btn secondary" type="button" @click="closeExecuteDialog">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>账号来源</label>
            <select v-model="executeForm.account_mode">
              <option value="default">使用默认账号（用例 &gt; 项目）</option>
              <option value="override">本次统一使用指定账号</option>
              <option value="none">不使用账号档案</option>
            </select>
          </div>
          <div class="field" v-show="executeForm.account_mode === 'override'">
            <label>本次统一账号</label>
            <select v-model="executeForm.account_profile_id">
              <option value="">请选择测试账号</option>
              <option v-for="acc in accounts" :key="acc.id" :value="String(acc.id)">
                {{ accountLabel(acc, projects) }}
              </option>
            </select>
          </div>
          <div class="field">
            <label>当前默认</label>
            <input type="text" :value="executeItem?.account_profile_name || '按项目默认账号解析'" disabled />
          </div>
          <label class="check-field">
            <input type="checkbox" v-model="executeForm.headed" />
            <span>弹出可见浏览器执行</span>
          </label>
        </div>
        <details class="functional-requirement">
          <summary>运行时变量</summary>
          <div class="form-grid">
            <div v-if="!variableFields.length" class="empty">没有需要手填的运行变量</div>
            <div v-for="field in variableFields" :key="field.name" class="field">
              <label>{{ field.label }}</label>
              <input
                :type="field.type || 'text'"
                :placeholder="field.placeholder || ''"
                v-model="executeForm.variables[field.name]"
              />
            </div>
          </div>
        </details>
        <details class="functional-requirement">
          <summary>临时覆盖账号/验证码</summary>
          <div class="form-grid">
            <div v-if="!accountFields.length" class="empty">没有需要手填的运行变量</div>
            <div v-for="field in accountFields" :key="field.name" class="field">
              <label>{{ field.label }}</label>
              <input
                :type="field.type || 'text'"
                :placeholder="field.placeholder || ''"
                v-model="executeForm.variables[field.name]"
              />
            </div>
          </div>
        </details>
      </div>
      <div class="modal-foot">
        <span></span>
        <button class="btn" type="submit" :disabled="executeSubmitting">
          {{ executeSubmitting ? '启动中...' : '可视化执行' }}
        </button>
      </div>
    </form>
  </dialog>

  <!-- 可视化执行进度弹窗（对齐旧应用 renderUiVisualExecution） -->
  <dialog ref="visualDialogEl" class="modal visual-modal" @close="onVisualDialogClose">
    <div v-if="visualRun">
      <div class="modal-head">
        <h3>可视化执行 {{ visualRun.case_name || executeItem?.case_name || '' }}</h3>
        <button class="btn secondary" type="button" @click="closeVisualDialog">关闭</button>
      </div>
      <div class="modal-body">
        <UiExecutionPanel
          :run="visualRun"
          :steps="visualSteps"
          :percent="visualPercent"
          :extracted-text="visualExtractedText"
          :status-text="visualStatusText"
          :step-result="visualStepResult"
          :short-value="visualShort"
        />
      </div>
      <div class="modal-foot">
        <span>{{ visualRun.updated_at ? '更新时间：' + visualRun.updated_at : '' }}</span>
        <div class="actions">
          <button v-if="visualRun.record_id" class="btn secondary" type="button" @click="goToRecords">查看记录</button>
          <button class="btn secondary" type="button" @click="closeVisualDialog">关闭</button>
        </div>
      </div>
    </div>
  </dialog>
  </div>
</template>

<script setup>
/**
 * UiCases 视图 — 迁移自旧应用 renderUiCases() + uiCaseForm() + openUiExecuteForm()
 *                + renderUiVisualExecution() + pollUiVisualExecution()
 *
 * 对齐项：
 * - 列表：columns（ID/项目/用例名称/页面地址/超时/测试账号/状态/操作）
 * - 筛选：仅项目筛选（无环境筛选、无搜索、无分页）
 * - CRUD：新增/编辑/删除（admin），表单字段与旧应用 uiCaseForm 完全一致
 * - 单条执行：openUiExecuteForm → POST /visual-execute → 轮询 /ui-executions/{run_id}
 * - 可视化执行进度：进度条 + 步骤表格 + 截图 + 事件日志
 * - 权限：admin 可见增删改按钮，normal 不可见
 * - 状态 Badge：badge()（active=ok / inactive=warn）
 * - 测试账号：保存后调用 saveTestAccountBinding(ui_case, id, accountProfileId)
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import AppTable from '../components/AppTable.vue'
import AppFormDialog from '../components/AppFormDialog.vue'
import UiCaseForm from '../components/ui-cases/UiCaseForm.vue'
import UiExecutionPanel from '../components/ui-cases/UiExecutionPanel.vue'
import UiRecordingPanel from '../components/ui-cases/UiRecordingPanel.vue'
import { WorkbenchPageHeader, WorkbenchPanel } from '../components/v2/workbench/index.js'
import { badgeText, badgeClass } from '../utils/badge.js'
import { accountLabel } from '../utils/account.js'
import * as uiCasesApi from '../api/modules/uiCases.js'
import { listTestAccounts, saveTestAccountBinding } from '../api/modules/testAccounts.js'

const router = useRouter()
const auth = useAuthStore()
const appStore = useAppStore()
const toast = useToastStore()

// ========== 状态 ==========
const projects = ref([])
const accounts = ref([])
const rows = ref([])
const loading = ref(false)
const filterProjectId = ref(appStore.filters.projectId || '')

// ========== 列定义（对齐旧应用 renderUiCases 表格列） ==========
const columns = [
  { key: 'id', label: 'ID' },
  { key: 'project_id', label: '项目', slot: 'project_id' },
  { key: 'case_name', label: '用例名称' },
  { key: 'page_url', label: '页面地址' },
  { key: 'timeout', label: '超时' },
  { key: 'account_profile_name', label: '测试账号', slot: 'account_profile_name' },
  { key: 'status', label: '状态', slot: 'status' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

// ========== 名称映射 ==========
function projectName(id) {
  const p = projects.value.find((item) => item.id === id)
  return p ? p.name : id
}

// ========== 数据加载 ==========
async function loadUiCases() {
  loading.value = true
  try {
    rows.value = await uiCasesApi.listUiCases(filterProjectId.value)
  } catch (error) {
    toast.show(error.message)
  } finally {
    loading.value = false
  }
}

// ========== 筛选切换 ==========
// 对齐旧应用 renderUiCases 项目切换：state.filters.projectId 变更 → 整体重载（含 accounts）
// 旧应用 line 3518-3522：select#uiProjectFilter change → renderUiCases() → 重新加载 accounts（带 project_id）
async function onProjectChange(event) {
  filterProjectId.value = event.target.value
  appStore.setProjectId(filterProjectId.value)
  // 重新加载账号列表，保证执行表单账号始终属于当前项目
  accounts.value = await listTestAccounts(filterProjectId.value)
  await loadUiCases()
}

// ========== CRUD 表单（对齐旧应用 uiCaseForm） ==========
const formVisible = ref(false)
const formTitle = ref('')
const formValues = ref({})
const editingItem = ref(null)

const projectOptions = computed(() =>
  projects.value.map((item) => ({ value: item.id, label: item.name })),
)

const accountOptions = computed(() => [
  { value: '', label: '跟随项目默认账号' },
  ...accounts.value.map((acc) => ({ value: acc.id, label: accountLabel(acc, projects.value) })),
])

const statusOptions = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '停用' },
]

const DEFAULT_STEPS = '[{"action":"goto","value":"https://example.com"},{"action":"text_assert","locator":"body","value":"Example"}]'

const formFields = computed(() => [
  { name: 'project_id', label: '项目', type: 'select', options: projectOptions.value, required: true },
  { name: 'case_name', label: '用例名称', required: true },
  { name: 'page_url', label: '页面地址', required: true },
  { name: 'steps', label: '步骤 JSON', type: 'textarea', rows: 8, default: DEFAULT_STEPS },
  { name: 'timeout', label: '超时秒数', type: 'number', default: 30 },
  { name: '__account_profile_id', label: '用例账号', type: 'select', options: accountOptions.value },
  { name: 'status', label: '状态', type: 'select', options: statusOptions, default: 'active' },
])

function openForm(item) {
  editingItem.value = item
  formTitle.value = item ? '编辑UI用例' : '新增UI用例'
  formValues.value = item
    ? { ...item, __account_profile_id: item.account_profile_id || '' }
    : {}
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingItem.value = null
}

async function submitForm(data) {
  try {
    const accountProfileId = data.__account_profile_id
    const payload = { ...data }
    delete payload.__account_profile_id
    const saved = editingItem.value
      ? await uiCasesApi.updateUiCase(editingItem.value.id, payload)
      : await uiCasesApi.createUiCase(payload)
    await saveTestAccountBinding('ui_case', saved.id, accountProfileId)
    toast.show('已保存')
    closeForm()
    await loadUiCases()
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 删除 ==========
async function onDelete(item) {
  if (!confirm('确认删除这条数据？')) return
  try {
    await uiCasesApi.deleteUiCase(item.id)
    toast.show('已删除')
    await loadUiCases()
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 可视化执行表单（对齐旧应用 openUiExecuteForm） ==========
const executeDialogEl = ref(null)
const executeVisible = ref(false)
const executeItem = ref(null)
const executeSubmitting = ref(false)
const executeForm = ref({
  account_mode: 'default',
  account_profile_id: '',
  headed: true,
  variables: {},
})

// 运行时变量字段元数据（对齐旧应用 FUNCTIONAL_RUNTIME_FIELD_META）
const RUNTIME_FIELD_META = {
  username: { label: '登录账号', placeholder: '请输入登录账号' },
  password: { label: '登录密码', type: 'password', placeholder: '请输入登录密码' },
  code: { label: '验证码', placeholder: '请输入验证码' },
  phone: { label: '手机号', placeholder: '请输入手机号' },
  email: { label: '邮箱', placeholder: '请输入邮箱' },
  account: { label: '账号', placeholder: '请输入账号' },
}

// 账号相关变量 key（对齐旧应用 ACCOUNT_RUNTIME_KEYS）
const ACCOUNT_RUNTIME_KEYS = new Set([
  'username', 'password', 'code', 'captcha', 'captcha_code',
  'verify_code', 'verification_code',
])

// 内置变量名（不作为运行时变量手填字段）
const BUILTIN_VARS = [
  'timestamp', 'datetime', 'date', 'uuid',
  'random_int', 'random_str', 'random_phone', 'random_email',
]

// 从 steps JSON 提取运行时变量字段（对齐旧应用 openUiExecuteForm 逻辑）
const runtimeFields = computed(() => {
  if (!executeItem.value) return []
  let steps = []
  try {
    steps = JSON.parse(executeItem.value.steps || '[]')
  } catch {
    steps = []
  }
  const text = JSON.stringify(steps)
  const names = new Set()
  text.replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\}\}/g, (_, name) => {
    names.add(name.replace(/^\$/, ''))
    return ''
  })
  ;['username', 'password', 'code'].forEach((name) => names.add(name))
  return [...names]
    .filter((name) => !BUILTIN_VARS.includes(name))
    .map((name) => {
      const meta = RUNTIME_FIELD_META[name] || {}
      return {
        name,
        label: meta.label || name,
        type: meta.type || 'text',
        placeholder: meta.placeholder || '',
      }
    })
})

const variableFields = computed(() =>
  runtimeFields.value.filter((field) => !ACCOUNT_RUNTIME_KEYS.has(field.name)),
)

const accountFields = computed(() =>
  runtimeFields.value.filter((field) => ACCOUNT_RUNTIME_KEYS.has(field.name)),
)

function onRun(item) {
  if (!item) return
  executeItem.value = item
  executeForm.value = {
    account_mode: 'default',
    account_profile_id: '',
    headed: true,
    variables: {},
  }
  executeVisible.value = true
  // 等待 DOM 更新后打开 dialog
  setTimeout(() => {
    if (executeDialogEl.value && !executeDialogEl.value.open) {
      executeDialogEl.value.showModal()
    }
  }, 0)
}

function closeExecuteDialog() {
  executeVisible.value = false
  if (executeDialogEl.value?.open) {
    executeDialogEl.value.close()
  }
}

function onExecuteDialogClose() {
  executeVisible.value = false
  executeSubmitting.value = false
}

async function submitExecuteForm() {
  if (!executeItem.value) return
  executeSubmitting.value = true
  try {
    // 对齐旧应用 readFunctionalExecutionForm
    const variables = {}
    ;[...variableFields.value, ...accountFields.value].forEach((field) => {
      const value = executeForm.value.variables[field.name]
      if (String(value ?? '').trim() !== '') variables[field.name] = value
    })
    const payload = {
      account_mode: executeForm.value.account_mode || 'default',
      account_profile_id:
        executeForm.value.account_mode === 'override' && executeForm.value.account_profile_id
          ? Number(executeForm.value.account_profile_id)
          : null,
      variables,
      headed: Boolean(executeForm.value.headed),
    }
    toast.show('正在启动可视化执行')
    const run = await uiCasesApi.visualExecuteUiCase(executeItem.value.id, payload)
    // 关闭执行表单，打开可视化进度弹窗
    closeExecuteDialog()
    startVisualPolling(run, executeItem.value)
  } catch (error) {
    toast.show(error.message)
  } finally {
    executeSubmitting.value = false
  }
}

// ========== 可视化执行进度轮询（对齐旧应用 startUiVisualPolling / pollUiVisualExecution） ==========
const visualDialogEl = ref(null)
const visualRun = ref(null)
const visualItem = ref(null)
let pollTimer = null

function startVisualPolling(run, item) {
  stopPolling()
  visualRun.value = run
  visualItem.value = item
  if (visualDialogEl.value && !visualDialogEl.value.open) {
    visualDialogEl.value.showModal()
  }
  pollTimer = window.setInterval(pollVisualExecution, 1000)
  pollVisualExecution()
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollVisualExecution() {
  if (!visualRun.value?.run_id) return
  try {
    const run = await uiCasesApi.getUiExecution(visualRun.value.run_id)
    visualRun.value = run
    if (run.status === 'passed' || run.status === 'failed') {
      stopPolling()
      toast.show(`执行完成：${run.status === 'passed' ? '成功' : '失败'}`)
    }
  } catch (error) {
    stopPolling()
    toast.show(error.message || '执行状态查询失败')
  }
}

function closeVisualDialog() {
  stopPolling()
  if (visualDialogEl.value?.open) {
    visualDialogEl.value.close()
  }
}

function onVisualDialogClose() {
  stopPolling()
  visualRun.value = null
}

function goToRecords() {
  closeVisualDialog()
  router.push('/records')
}

// ========== 可视化执行渲染辅助（对齐旧应用 uiVisual* 函数） ==========
function visualStatusText(status) {
  const map = {
    queued: '排队中',
    running: '执行中',
    passed: '成功',
    failed: '失败',
    error: '失败',
  }
  return map[status] || status || '-'
}

const visualPercent = computed(() => {
  const run = visualRun.value
  if (!run) return 0
  const steps = run.steps || []
  if (run.status === 'passed' || run.status === 'failed') return 100
  if (!steps.length) return run.status === 'running' ? 20 : 5
  const done = steps.filter(
    (item) => ['passed', 'failed', 'skipped'].includes(item.status),
  ).length
  return Math.max(8, Math.min(95, Math.round((done / steps.length) * 100)))
})

const visualSteps = computed(() => visualRun.value?.steps || [])

const visualExtractedText = computed(() => {
  const extracted = visualRun.value?.extracted_vars || {}
  if (!extracted || !Object.keys(extracted).length) return '暂无提取数据'
  return JSON.stringify(extracted, null, 2)
})

function visualShort(value, max = 140) {
  const text = String(value ?? '')
  return text.length > max ? text.slice(0, max) + '...' : text
}

function visualStepResult(step) {
  if (step.error) return step.error
  if (step.reason) return step.reason
  if (step.extracted && Object.keys(step.extracted).length) {
    return JSON.stringify(step.extracted)
  }
  return ''
}

function visualStepClass(status) {
  if (status === 'passed') return 'ok'
  if (status === 'failed' || status === 'error') return 'fail'
  if (status === 'running' || status === 'queued') return 'warn'
  return badgeClass(status)
}

// ========== 生命周期 ==========
onMounted(async () => {
  if (!auth.user) {
    await auth.fetchMe()
  }
  const projectList = await appStore.fetchProjects()
  projects.value = projectList
  appStore.setProjects(projectList)
  // 加载测试账号（对齐旧应用 api('/api/test-accounts?project_id=...')）
  accounts.value = await listTestAccounts(filterProjectId.value)
  await loadUiCases()
})

onBeforeUnmount(() => {
  stopPolling()
  stopRecordPolling()
})

// ========== 录制UI用例（对齐旧应用 openUiRecordStartDialog + startUiRecordPolling + openUiRecordSaveDialog） ==========
// 旧应用 static/app.js line 3453-3481：openUiRecordStartDialog → openForm → POST /api/ui-record/sessions
// 旧应用 line 3334-3351：pollUiRecordSession + startUiRecordPolling（1s 轮询 GET /events）
// 旧应用 line 3353-3365：cancelUiRecordSession（DELETE 会话）
// 旧应用 line 3367-3422：openUiRecordSaveDialog → POST /sessions/{id}/save
const recordStartVisible = ref(false)
const recordStartValues = ref({})
const recordDialogEl = ref(null)
const recordVisible = ref(false)
const recordSaveDialogEl = ref(null)
const recordSaveVisible = ref(false)
const recordSession = ref({})
const recordPreviewRows = ref([])
const recordSaveForm = ref({ assertion_text: '' })
const recordSaving = ref(false)
let recordPollTimer = null
let recordSessionId = ''

// 启动表单字段（对齐旧应用 openUiRecordStartDialog → openForm 字段定义）
const recordStartFields = computed(() => [
  { name: 'project_id', label: '项目', type: 'select', options: projectOptions.value, required: true },
  {
    name: 'account_profile_id',
    label: '测试账号（首次登录后自动保存登录态）',
    type: 'select',
    options: [
      { value: '', label: '不复用登录态' },
      ...accounts.value.map((acc) => ({ value: acc.id, label: accountLabel(acc, projects.value) })),
    ],
  },
  { name: 'case_name', label: '用例名称', required: true },
  { name: 'start_url', label: '起始URL', required: true },
])

// 截断显示（对齐旧应用 uiRecordShort，max=120）
function recordShort(value, max = 120) {
  const text = typeof value === 'string' ? value : JSON.stringify(value ?? '')
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function openRecordStartDialog() {
  if (!projects.value.length) {
    toast.show('请先创建项目')
    return
  }
  recordStartValues.value = {
    project_id: filterProjectId.value || projects.value[0]?.id || '',
  }
  recordStartVisible.value = true
}

function closeRecordStart() {
  recordStartVisible.value = false
}

// 启动录制（对齐旧应用 line 3473-3478）
async function submitRecordStart(data) {
  try {
    toast.show('正在启动可视化浏览器')
    const session = await uiCasesApi.startUiRecordSession(data)
    toast.show('录制已开始')
    recordStartVisible.value = false
    startRecordPolling(session)
  } catch (error) {
    toast.show(error.message || '启动录制失败')
  }
  // 返回 false 阻止 AppFormDialog 自动关闭（旧应用同样 return false）
  return false
}

// 启动轮询（对齐旧应用 startUiRecordPolling line 3345-3351）
function startRecordPolling(session) {
  stopRecordPolling()
  recordSessionId = session.session_id || ''
  recordSession.value = session
  recordPreviewRows.value = session.preview_steps || []
  recordVisible.value = true
  if (recordDialogEl.value && !recordDialogEl.value.open) {
    recordDialogEl.value.showModal()
  }
  recordPollTimer = window.setInterval(pollRecordSession, 1000)
  pollRecordSession()
}

// 轮询事件（对齐旧应用 pollUiRecordSession line 3334-3343）
async function pollRecordSession() {
  if (!recordSessionId) return
  try {
    const data = await uiCasesApi.getUiRecordEvents(recordSessionId)
    recordSession.value = { ...recordSession.value, ...data }
    recordPreviewRows.value = data?.preview_steps || []
  } catch (error) {
    stopRecordPolling()
    toast.show(error.message || '录制状态查询失败')
  }
}

function stopRecordPolling() {
  if (recordPollTimer) {
    clearInterval(recordPollTimer)
    recordPollTimer = null
  }
}

// 取消录制（对齐旧应用 cancelUiRecordSession line 3353-3365）
async function cancelRecordSession() {
  const sessionId = recordSessionId
  stopRecordPolling()
  recordSessionId = ''
  recordVisible.value = false
  if (recordDialogEl.value && recordDialogEl.value.open) {
    recordDialogEl.value.close()
  }
  if (sessionId) {
    try {
      await uiCasesApi.cancelUiRecordSession(sessionId)
    } catch (error) {
      toast.show(error.message || '取消录制失败')
    }
  }
}

function onRecordDialogClose() {
  // 用户按 ESC 关闭弹窗时，等同取消录制
  if (recordSessionId) {
    stopRecordPolling()
    cancelRecordSession()
  }
}

// 打开保存弹窗（对齐旧应用 openUiRecordSaveDialog line 3367-3400）
function openRecordSaveDialog() {
  stopRecordPolling()
  recordSaveForm.value = { assertion_text: '' }
  recordSaveVisible.value = true
  if (recordSaveDialogEl.value && !recordSaveDialogEl.value.open) {
    recordSaveDialogEl.value.showModal()
  }
}

function closeRecordSaveDialog() {
  recordSaveVisible.value = false
  if (recordSaveDialogEl.value && recordSaveDialogEl.value.open) {
    recordSaveDialogEl.value.close()
  }
}

function onRecordSaveDialogClose() {
  recordSaveVisible.value = false
}

// 返回录制（对齐旧应用 line 3402-3404）
function backToRecord() {
  closeRecordSaveDialog()
  if (recordSessionId) {
    recordVisible.value = true
    if (recordDialogEl.value && !recordDialogEl.value.open) {
      recordDialogEl.value.showModal()
    }
    recordPollTimer = window.setInterval(pollRecordSession, 1000)
    pollRecordSession()
  }
}

// 提交保存（对齐旧应用 line 3405-3422）
async function submitRecordSave() {
  if (recordSaving.value) return
  recordSaving.value = true
  try {
    const result = await uiCasesApi.saveUiRecordSession(recordSessionId, recordSaveForm.value)
    recordSessionId = ''
    recordSession.value = {}
    recordPreviewRows.value = []
    toast.show(`已保存UI用例 #${result.case?.id || ''}`)
    closeRecordSaveDialog()
    if (recordDialogEl.value && recordDialogEl.value.open) {
      recordDialogEl.value.close()
    }
    await loadUiCases()
  } catch (error) {
    toast.show(error.message || '保存录制失败')
  } finally {
    recordSaving.value = false
  }
}
</script>

<style scoped>
.v2-ui-cases {
  display: grid;
  gap: 12px;
  width: 100%;
  max-width: none;
  margin: 0;
}

.v2-ui-cases :deep(.v2-workbench-page-header__eyebrow) {
  color: #64748b;
  font-size: 11px;
  letter-spacing: 0.1em;
}

.v2-ui-cases :deep(.v2-workbench-page-header__title) {
  font-size: 26px;
  font-weight: 650;
  line-height: 1.25;
}

.v2-ui-cases :deep(.v2-workbench-panel) {
  min-width: 0;
  gap: 10px;
}

.v2-ui-cases :deep(.v2-workbench-panel__header) {
  min-height: 0;
  padding: 0 2px;
}

.v2-ui-cases :deep(.v2-workbench-panel__body) {
  min-height: calc(var(--v2-size-table-row) * 4 + var(--v2-size-table-header));
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
}

.v2-ui-cases :deep(.v2-base-empty-state) {
  min-height: 160px;
  justify-content: center;
}

.v2-ui-cases :deep(.v2-base-empty-state__icon) {
  width: 56px;
  height: 56px;
  color: #94a3b8;
  background: #f1f5f9;
}

.v2-ui-cases :deep(.v2-app-table__table) {
  font-variant-numeric: tabular-nums;
}

.v2-ui-cases :deep(.v2-app-table__header) {
  height: 40px;
  padding: 0 12px;
  font-size: 11px;
}

.v2-ui-cases :deep(.v2-app-table__cell) {
  height: 44px;
  padding: 0 12px;
  font-size: 13px;
}

.toolbar,
.filters,
.actions,
.modal-head,
.modal-foot,
.progress-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.toolbar,
.modal-head,
.modal-foot,
.progress-meta {
  justify-content: space-between;
}

.toolbar {
  padding: 12px 16px;
  border-bottom: 1px solid var(--v2-border-panel);
  background: #ffffff;
}

.field,
.form-grid,
.functional-requirement,
.summary-detail {
  display: grid;
  gap: var(--v2-space-1);
}

.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v2-space-3);
}

.field label,
.modal-foot,
.progress-meta span {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
  font-weight: var(--v2-font-weight-semibold);
}

input,
select,
.btn {
  min-height: var(--v2-control-height-compact);
  border: var(--v2-border-width) solid var(--v2-border-default);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-default);
  color: var(--v2-text-secondary);
  font: inherit;
  font-size: var(--v2-font-size-caption);
}

input,
select {
  width: 100%;
  padding: 0 var(--v2-space-2);
}

.btn {
  padding: 0 var(--v2-space-2);
  cursor: pointer;
  font-weight: var(--v2-font-weight-semibold);
}

.btn:not(.secondary):not(.danger) {
  border-color: var(--v2-action-primary);
  background: var(--v2-action-primary);
  color: var(--v2-text-inverse);
}

.btn.danger {
  border-color: var(--v2-feedback-danger);
  background: var(--v2-feedback-danger-soft);
  color: var(--v2-feedback-danger);
}

.btn:focus-visible,
input:focus-visible,
select:focus-visible,
summary:focus-visible {
  outline: 0;
  box-shadow: var(--v2-state-focus-ring);
}

.badge {
  display: inline-flex;
  min-height: var(--v2-icon-size-md);
  align-items: center;
  padding: 0 var(--v2-space-1);
  border-radius: var(--v2-radius-round);
  background: var(--v2-surface-soft);
  color: var(--v2-text-secondary);
  font-size: var(--v2-font-size-tiny);
  font-weight: var(--v2-font-weight-semibold);
}

.badge.ok {
  background: var(--v2-feedback-success-soft);
  color: var(--v2-feedback-success);
}

.badge.warn {
  background: var(--v2-feedback-warning-soft);
  color: var(--v2-feedback-warning);
}

.badge.fail,
.badge.error {
  background: var(--v2-feedback-danger-soft);
  color: var(--v2-feedback-danger);
}

.modal {
  width: min(calc(var(--v2-space-7) * 11), 94vw);
  max-width: 94vw;
  max-height: 90vh;
  overflow: hidden;
  padding: 0;
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-default);
  color: var(--v2-text-primary);
  box-shadow: var(--v2-shadow-overlay);
}

.modal::backdrop {
  background: var(--v2-surface-overlay);
}

.modal-head,
.modal-foot {
  padding: var(--v2-space-3);
}

.modal-head {
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
}

.modal-head h3,
.panel-title h3 {
  margin: 0;
  color: var(--v2-text-primary);
  font-size: var(--v2-font-size-body);
  font-weight: var(--v2-font-weight-semibold);
}

.modal-body {
  max-height: calc(90vh - var(--v2-space-7) * 2);
  overflow: auto;
  padding: var(--v2-space-3);
}

.modal-foot {
  border-top: var(--v2-border-width) solid var(--v2-border-panel);
}

.diagnosis-summary,
.functional-requirement,
.summary-detail,
.alert,
.panel {
  margin-top: var(--v2-space-3);
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: color-mix(in srgb, var(--v2-surface-workspace) 62%, var(--v2-surface-default));
}

.diagnosis-summary div,
.functional-execution-summary,
.functional-two-col {
  display: grid;
  gap: var(--v2-space-2);
}

.diagnosis-summary div {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: var(--v2-space-2);
}

.functional-execution-summary {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.functional-execution-summary div {
  display: grid;
  gap: var(--v2-space-micro);
  padding: var(--v2-space-2);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-default);
}

.functional-execution-summary span {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
}

.functional-two-col {
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, .75fr);
  margin-top: var(--v2-space-3);
}

.table-wrap {
  max-width: 100%;
  overflow-x: auto;
}

table {
  width: 100%;
  border-spacing: 0;
  border-collapse: separate;
  color: var(--v2-text-secondary);
  font-size: var(--v2-font-size-caption);
  text-align: left;
}

th,
td {
  padding: var(--v2-space-2);
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
}

th {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
  letter-spacing: var(--v2-letter-spacing-wide);
}

.progress-track {
  overflow: hidden;
  height: var(--v2-space-1);
  margin-top: var(--v2-space-1);
  border-radius: var(--v2-radius-round);
  background: var(--v2-surface-pressed);
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--v2-action-primary);
  transition: width var(--v2-motion-duration-dialog) var(--v2-motion-easing-standard);
}

.progress-fill.failed {
  background: var(--v2-feedback-danger);
}

.mini-log,
.log-view {
  max-height: calc(var(--v2-space-7) * 5);
  overflow: auto;
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-workspace);
  color: var(--v2-text-secondary);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.empty {
  padding: var(--v2-space-5);
  color: var(--v2-text-muted);
  text-align: center;
}

.v2-ui-cases__screenshot {
  width: 100%;
  max-height: calc(var(--v2-space-7) * 6.5);
  object-fit: contain;
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-default);
}

.visual-modal {
  max-width: 1100px;
  width: 96vw;
}

@media (max-width: 900px) {
  .form-grid,
  .functional-two-col,
  .functional-execution-summary {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .progress-fill {
    transition-duration: var(--v2-motion-reduced);
  }
}
</style>
