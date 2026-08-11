<template>
  <!-- 对齐旧应用 renderProjects()：项目列表 + 环境配置 + 测试账号档案 三段式布局 -->
  <div class="v2-projects">
  <WorkbenchPageHeader
    eyebrow="WORKSPACE"
    title="项目空间"
    description="集中维护项目、执行环境与测试账号绑定；普通成员保持只读访问。"
  >
    <template #actions>
      <button v-if="auth.isAdmin" class="btn" @click="openProjectForm(null)">新增项目</button>
    </template>
  </WorkbenchPageHeader>

  <WorkbenchPanel title="项目" :subtitle="auth.isAdmin ? '可配置项目与默认测试账号' : '当前账号只读'">
  <AppTable :columns="projectColumns" :rows="rows.projects">
    <template #account_profile_name="{ row }">
      {{ row.account_profile_name || '-' }}
    </template>
    <template #actions="{ row }">
      <div v-if="auth.isAdmin" class="actions">
        <button class="btn secondary" @click="openAccountBinding(row)">账号</button>
        <button class="btn secondary" @click="openProjectForm(row)">编辑</button>
        <button class="btn danger" @click="onDeleteProject(row)">删除</button>
      </div>
      <span v-else>-</span>
    </template>
  </AppTable>
  </WorkbenchPanel>

  <!-- 项目环境配置 -->
  <WorkbenchPanel title="环境配置" subtitle="按项目维护 Base URL、超时与公共变量">
    <div class="toolbar">
      <div class="filters">
        <div class="field compact">
          <label>项目环境配置</label>
          <select v-model="envFilterProjectId" @change="onEnvFilterChange">
            <option value="">全部项目</option>
            <option v-for="p in rows.projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </div>
      </div>
      <button v-if="auth.isAdmin" class="btn" @click="openEnvForm(null)">新增环境</button>
    </div>

    <AppTable :columns="envColumns" :rows="envRows">
      <template #project_id="{ row }">
        {{ projectName(row.project_id) }}
      </template>
      <template #global_headers="{ row }">
        {{ short(row.global_headers) }}
      </template>
      <template #global_vars="{ row }">
        {{ short(row.global_vars) }}
      </template>
      <template #actions="{ row }">
        <div v-if="auth.isAdmin" class="actions">
          <button class="btn secondary" @click="openEnvForm(row)">编辑</button>
          <button class="btn danger" @click="onDeleteEnv(row)">删除</button>
        </div>
        <span v-else>-</span>
      </template>
    </AppTable>
  </WorkbenchPanel>

  <!-- 测试账号档案 -->
  <WorkbenchPanel title="测试账号档案" subtitle="敏感信息保持掩码显示">
    <div class="toolbar">
      <div class="filters"><strong>测试账号档案</strong></div>
      <button v-if="auth.isAdmin" class="btn" @click="openTestAccountForm(null)">新增测试账号</button>
    </div>

    <AppTable :columns="accountColumns" :rows="rows.accounts">
      <template #project_id="{ row }">
        {{ row.project_id ? projectName(row.project_id) : '全局' }}
      </template>
      <template #masked_variables="{ row }">
        <pre class="mini-log">{{ accountMaskedText(row) }}</pre>
      </template>
      <template #status="{ row }">
        <span class="badge" :class="badgeClass(row.status)">{{ badgeText(row.status) }}</span>
      </template>
      <template #actions="{ row }">
        <div v-if="auth.isAdmin" class="actions">
          <button class="btn secondary" @click="openTestAccountForm(row)">编辑</button>
          <button class="btn danger" @click="onDeleteTestAccount(row)">删除</button>
        </div>
        <span v-else>-</span>
      </template>
    </AppTable>
  </WorkbenchPanel>

  <!-- 项目表单弹窗 -->
  <AppFormDialog
    :visible="projectFormVisible"
    :title="projectFormTitle"
    :fields="projectFormFields"
    :values="projectFormValues"
    @close="closeProjectForm"
    @submit="submitProjectForm"
  />

  <!-- 环境表单弹窗 -->
  <AppFormDialog
    :visible="envFormVisible"
    :title="envFormTitle"
    :fields="envFormFields"
    :values="envFormValues"
    @close="closeEnvForm"
    @submit="submitEnvForm"
  />

  <!-- 测试账号表单弹窗 -->
  <AppFormDialog
    :visible="accountFormVisible"
    :title="accountFormTitle"
    :fields="accountFormFields"
    :values="accountFormValues"
    @close="closeAccountForm"
    @submit="submitAccountForm"
  />

  <!-- 账号绑定弹窗 -->
  <AppFormDialog
    :visible="bindingFormVisible"
    :title="bindingFormTitle"
    :fields="bindingFormFields"
    :values="bindingFormValues"
    submit-label="保存"
    @close="closeBindingForm"
    @submit="submitBindingForm"
  />
  </div>
</template>

<script setup>
/**
 * Projects 视图 — 迁移自旧应用 renderProjects()
 *
 * 对齐项：
 * - 三段式布局：项目列表 + 项目环境配置 + 测试账号档案
 * - 权限：admin 可增删改，normal 只读
 * - 项目筛选：环境配置区有项目筛选下拉框，写入 localStorage('projectId')
 * - API：/api/projects, /api/envs, /api/test-accounts, /api/test-account-bindings
 * - 表单：projectForm / envForm / openTestAccountForm / openAccountBindingForm
 * - 删除：使用 confirm 确认（对齐旧应用 deleteItem）
 */
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import AppTable from '../components/AppTable.vue'
import AppFormDialog from '../components/AppFormDialog.vue'
import { WorkbenchPageHeader, WorkbenchPanel } from '../components/v2/workbench/index.js'
import { badgeText, badgeClass } from '../utils/badge.js'
import { accountMaskedText, accountLabel } from '../utils/account.js'
import * as projectsApi from '../api/modules/projects.js'
import * as envsApi from '../api/modules/envs.js'
import * as testAccountsApi from '../api/modules/testAccounts.js'

const auth = useAuthStore()
const appStore = useAppStore()
const toast = useToastStore()

// 三段数据
const rows = ref({ projects: [], envs: [], accounts: [] })

// 环境筛选 projectId（对齐旧应用 state.filters.projectId + #projectEnvFilter）
const envFilterProjectId = ref(appStore.filters.projectId || '')

// ========== 列定义 ==========
const projectColumns = [
  { key: 'id', label: 'ID' },
  { key: 'name', label: '项目名称' },
  { key: 'desc', label: '描述' },
  { key: 'account_profile_name', label: '默认测试账号', slot: 'account_profile_name' },
  { key: 'create_time', label: '创建时间' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

const envColumns = [
  { key: 'id', label: 'ID' },
  { key: 'project_id', label: '项目', slot: 'project_id' },
  { key: 'env_name', label: '环境名称' },
  { key: 'base_url', label: 'Base URL' },
  { key: 'timeout', label: '超时' },
  { key: 'global_headers', label: '全局请求头', slot: 'global_headers' },
  { key: 'global_vars', label: '全局变量', slot: 'global_vars' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

const accountColumns = [
  { key: 'id', label: 'ID' },
  { key: 'profile_name', label: '账号档案' },
  { key: 'project_id', label: '范围', slot: 'project_id' },
  { key: 'masked_variables', label: '变量', slot: 'masked_variables' },
  { key: 'status', label: '状态', slot: 'status' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

// ========== 辅助函数 ==========
function projectName(id) {
  const p = rows.value.projects.find((item) => item.id === id)
  return p?.name || id
}

function short(value, length = 140) {
  const s = String(value ?? '')
  return s.length > length ? s.slice(0, length) + '...' : s
}

// 环境筛选后的行（对齐旧应用 envRows = projectId ? allEnvs.filter(...) : allEnvs）
const envRows = computed(() => {
  if (!envFilterProjectId.value) return rows.value.envs
  return rows.value.envs.filter((item) => String(item.project_id) === String(envFilterProjectId.value))
})

// ========== 数据加载 ==========
async function loadAll() {
  try {
    const [projects, envs, accounts] = await Promise.all([
      projectsApi.listProjects(),
      envsApi.listEnvs(),
      testAccountsApi.listTestAccounts(appStore.filters.projectId),
    ])
    rows.value = { projects, envs, accounts }
    // 同步 appStore 缓存（对齐旧应用 _projectsCache）
    appStore.setProjects(projects)
  } catch (error) {
    toast.show(error.message)
  }
}

async function reloadProjects() {
  const projects = await projectsApi.listProjects()
  rows.value.projects = projects
  appStore.setProjects(projects)
}

// ========== 项目表单 ==========
const projectFormVisible = ref(false)
const editingProject = ref(null)
const projectFormValues = ref({})
const projectFormTitle = computed(() => (editingProject.value ? '编辑项目' : '新增项目'))
const projectFormFields = [
  { name: 'name', label: '项目名称', required: true },
  { name: 'desc', label: '描述', type: 'textarea' },
]

function openProjectForm(item) {
  editingProject.value = item
  projectFormValues.value = item ? { name: item.name, desc: item.desc } : {}
  projectFormVisible.value = true
}

function closeProjectForm() {
  projectFormVisible.value = false
  editingProject.value = null
  projectFormValues.value = {}
}

async function submitProjectForm(data) {
  try {
    if (editingProject.value) {
      await projectsApi.updateProject(editingProject.value.id, data)
    } else {
      await projectsApi.createProject(data)
    }
    appStore.invalidateProjectsCache()
    toast.show('已保存')
    closeProjectForm()
    await reloadProjects()
  } catch (error) {
    toast.show(error.message)
  }
}

async function onDeleteProject(item) {
  if (!confirm(`确认删除项目 ${item.name}？此操作会级联删除相关数据。`)) return
  try {
    await projectsApi.deleteProject(item.id)
    appStore.invalidateProjectsCache()
    toast.show('已删除')
    await loadAll()
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 环境表单 ==========
const envFormVisible = ref(false)
const editingEnv = ref(null)
const envFormValues = ref({})
const envFormTitle = computed(() => (editingEnv.value ? '编辑环境' : '新增环境'))
const envFormFields = computed(() => {
  const projectOptions = rows.value.projects.map((p) => ({ value: p.id, label: p.name }))
  return [
    { name: 'project_id', label: '项目', type: 'select', options: projectOptions, required: true },
    { name: 'env_name', label: '环境名称', required: true },
    { name: 'base_url', label: 'Base URL', required: true },
    { name: 'global_headers', label: '全局请求头 JSON', type: 'textarea', default: '{}' },
    { name: 'global_vars', label: '全局变量 JSON', type: 'textarea', default: '{}' },
    { name: 'timeout', label: '超时秒数', type: 'number', default: 30 },
  ]
})

function openEnvForm(item) {
  editingEnv.value = item
  envFormValues.value = item
    ? { ...item }
    : { project_id: envFilterProjectId.value || rows.value.projects[0]?.id || '', timeout: 30, global_headers: '{}', global_vars: '{}' }
  envFormVisible.value = true
}

function closeEnvForm() {
  envFormVisible.value = false
  editingEnv.value = null
  envFormValues.value = {}
}

async function submitEnvForm(data) {
  try {
    // timeout 转 number（对齐旧应用后端期望）
    if (data.timeout) data.timeout = Number(data.timeout)
    if (data.project_id) data.project_id = Number(data.project_id)
    if (editingEnv.value) {
      await envsApi.updateEnv(editingEnv.value.id, data)
    } else {
      await envsApi.createEnv(data)
    }
    toast.show('已保存')
    closeEnvForm()
    await loadAll()
  } catch (error) {
    toast.show(error.message)
  }
}

async function onDeleteEnv(item) {
  if (!confirm(`确认删除环境 ${item.env_name}？`)) return
  try {
    await envsApi.deleteEnv(item.id)
    toast.show('已删除')
    await loadAll()
  } catch (error) {
    toast.show(error.message)
  }
}

// 环境筛选切换（对齐旧应用 #projectEnvFilter change → state.filters.projectId + localStorage）
function onEnvFilterChange() {
  appStore.setProjectId(envFilterProjectId.value)
}

// ========== 测试账号表单 ==========
const accountFormVisible = ref(false)
const editingAccount = ref(null)
const accountFormValues = ref({})
const accountFormTitle = computed(() => (editingAccount.value ? '编辑测试账号' : '新增测试账号'))
const accountFormFields = computed(() => {
  const isEdit = !!editingAccount.value
  const projectOptions = [
    { value: '', label: '全局账号' },
    ...rows.value.projects.map((p) => ({ value: p.id, label: p.name })),
  ]
  return [
    { name: 'project_id', label: '所属项目', type: 'select', options: projectOptions },
    { name: 'profile_name', label: '账号档案名称', required: true },
    { name: 'username', label: '登录账号', required: true },
    { name: 'password', label: isEdit ? '登录密码（留空不修改）' : '登录密码', type: 'password' },
    { name: 'code', label: isEdit ? '验证码（留空不修改）' : '验证码' },
    { name: 'login_url', label: '登录页 URL', placeholder: '留空时默认按目标站点自动拼接 /login' },
    { name: 'username_locator', label: '账号输入框定位器', type: 'textarea', rows: 4, placeholder: '支持一行一个，按顺序兜底匹配' },
    { name: 'password_locator', label: '密码输入框定位器', type: 'textarea', rows: 3, placeholder: '支持一行一个，按顺序兜底匹配' },
    { name: 'submit_locator', label: '登录按钮定位器', type: 'textarea', rows: 4, placeholder: '支持一行一个，按顺序兜底匹配' },
    { name: 'success_url_contains', label: '登录成功 URL 关键字', placeholder: '例如 /customerHasBeenInvited，选填' },
    { name: 'success_selector', label: '登录成功元素定位器', placeholder: '例如 text=已邀请客户，选填' },
    {
      name: 'status',
      label: '状态',
      type: 'select',
      options: [
        { value: 'active', label: '启用' },
        { value: 'inactive', label: '停用' },
      ],
    },
  ]
})

// 定位器默认值（对齐旧应用 openTestAccountForm values）
const DEFAULT_USERNAME_LOCATOR = 'input[placeholder="邮箱/手机号"]\ninput[name="username"]\ninput[name="account"]\ninput[name="mobile"]\ninput[name="email"]\ninput[type="text"]'
const DEFAULT_PASSWORD_LOCATOR = 'input[placeholder="请输入密码"]\ninput[type="password"]\ninput[name="password"]'
const DEFAULT_SUBMIT_LOCATOR = 'button[type="submit"]\nbutton:has-text("登录")\n[role="button"]:has-text("登录")\ntext=登录'

function openTestAccountForm(item) {
  editingAccount.value = item
  const currentVariables = item?.variables || {}
  accountFormValues.value = {
    project_id: item?.project_id || '',
    profile_name: item?.profile_name || '',
    username: currentVariables.username || currentVariables.account || '',
    password: '',
    code: '',
    login_url: item?.login_url || '',
    username_locator: item?.username_locator || DEFAULT_USERNAME_LOCATOR,
    password_locator: item?.password_locator || DEFAULT_PASSWORD_LOCATOR,
    submit_locator: item?.submit_locator || DEFAULT_SUBMIT_LOCATOR,
    success_url_contains: item?.success_url_contains || '',
    success_selector: item?.success_selector || '',
    status: item?.status || 'active',
  }
  accountFormVisible.value = true
}

function closeAccountForm() {
  accountFormVisible.value = false
  editingAccount.value = null
  accountFormValues.value = {}
}

async function submitAccountForm(data) {
  try {
    const body = {
      project_id: data.project_id ? Number(data.project_id) : null,
      profile_name: data.profile_name,
      variables: {
        username: String(data.username || '').trim(),
      },
      login_url: String(data.login_url || '').trim(),
      username_locator: String(data.username_locator || '').trim(),
      password_locator: String(data.password_locator || '').trim(),
      submit_locator: String(data.submit_locator || '').trim(),
      success_url_contains: String(data.success_url_contains || '').trim(),
      success_selector: String(data.success_selector || '').trim(),
      status: data.status || 'active',
    }
    const sensitive = {}
    if (String(data.password || '').trim()) sensitive.password = data.password
    if (String(data.code || '').trim()) sensitive.code = data.code
    // 对齐旧应用：新增时始终传 sensitive_variables（即使为空），编辑时仅在有敏感字段时传
    if (!editingAccount.value || Object.keys(sensitive).length) {
      body.sensitive_variables = sensitive
    }
    if (editingAccount.value) {
      await testAccountsApi.updateTestAccount(editingAccount.value.id, body)
    } else {
      await testAccountsApi.createTestAccount(body)
    }
    toast.show('测试账号已保存')
    closeAccountForm()
    await loadAll()
  } catch (error) {
    toast.show(error.message)
  }
}

async function onDeleteTestAccount(item) {
  if (!confirm(`确认删除测试账号 ${item.profile_name}？`)) return
  try {
    await testAccountsApi.deleteTestAccount(item.id)
    toast.show('已删除')
    await loadAll()
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 账号绑定表单 ==========
const bindingFormVisible = ref(false)
const bindingTarget = ref(null) // { type, id, currentId }
const bindingFormValues = ref({})
const bindingFormTitle = computed(() => `设置项目默认账号：${bindingTarget.value?.name || ''}`)
const bindingFormFields = computed(() => {
  return [
    {
      name: 'account_profile_id',
      label: '测试账号',
      type: 'select',
      options: [
        { value: '', label: '不设置默认账号' },
        ...rows.value.accounts.map((item) => ({
          value: item.id,
          label: accountLabel(item, rows.value.projects),
        })),
      ],
    },
  ]
})

function openAccountBinding(project) {
  bindingTarget.value = project
  bindingFormValues.value = { account_profile_id: project.account_profile_id || '' }
  bindingFormVisible.value = true
}

function closeBindingForm() {
  bindingFormVisible.value = false
  bindingTarget.value = null
  bindingFormValues.value = {}
}

async function submitBindingForm(data) {
  try {
    await testAccountsApi.saveTestAccountBinding('project', bindingTarget.value.id, data.account_profile_id)
    appStore.invalidateProjectsCache()
    toast.show('测试账号已保存')
    closeBindingForm()
    await loadAll()
  } catch (error) {
    toast.show(error.message)
  }
}

// ========== 生命周期 ==========
onMounted(async () => {
  if (!auth.user) {
    await auth.fetchMe()
  }
  await loadAll()
})
</script>

<style scoped>
.v2-projects {
  display: grid;
  gap: var(--v2-space-3);
  max-width: var(--v2-layout-workspace-max);
  margin: 0 auto;
}

.toolbar,
.filters,
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--v2-space-2);
}

.toolbar {
  justify-content: space-between;
  padding: var(--v2-space-2) var(--v2-space-3);
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
}

.btn {
  min-height: var(--v2-control-height-compact);
  padding: 0 var(--v2-space-2);
  border: var(--v2-border-width) solid var(--v2-action-primary);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-action-primary);
  color: var(--v2-text-inverse);
  cursor: pointer;
  font: inherit;
  font-size: var(--v2-font-size-caption);
  font-weight: var(--v2-font-weight-semibold);
}

.btn.secondary {
  border-color: var(--v2-border-default);
  background: var(--v2-surface-default);
  color: var(--v2-text-secondary);
}

.btn.danger {
  border-color: var(--v2-feedback-danger);
  background: var(--v2-feedback-danger-soft);
  color: var(--v2-feedback-danger);
}

.btn:hover {
  background: var(--v2-action-primary-hover);
}

.btn.secondary:hover {
  background: var(--v2-surface-hover);
}

.btn.danger:hover {
  background: var(--v2-feedback-danger-soft);
}

.btn:focus-visible,
select:focus-visible {
  outline: 0;
  box-shadow: var(--v2-state-focus-ring);
}

.field {
  display: grid;
  gap: var(--v2-space-micro);
}

.field label {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
  font-weight: var(--v2-font-weight-semibold);
}

select {
  min-height: var(--v2-control-height-compact);
  padding: 0 var(--v2-space-2);
  border: var(--v2-border-width) solid var(--v2-border-default);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-default);
  color: var(--v2-text-primary);
  font: inherit;
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

.badge.fail {
  background: var(--v2-feedback-danger-soft);
  color: var(--v2-feedback-danger);
}

.mini-log {
  max-width: calc(var(--v2-space-7) * 5);
  margin: 0;
  overflow: hidden;
  color: var(--v2-text-muted);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
