<template>
  <!-- 对齐旧应用 renderRecords()：工具栏 + 表格 + 分页 -->
  <div class="v2-records">
  <WorkbenchPageHeader
    eyebrow="EXECUTION"
    title="执行报告"
    description="筛选并复查接口、UI 与数据任务的执行证据，保留再次执行、日志、报告和截图入口。"
  />
  <WorkbenchPanel title="执行记录" :subtitle="`共 ${total} 条记录`">
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
        <label>类型</label>
        <select :value="filterType" @change="onTypeChange">
          <option value="">全部</option>
          <option value="api">api</option>
          <option value="ui">ui</option>
        </select>
      </div>
    </div>
  </div>

  <AppTable :columns="recordColumns" :rows="rows">
    <template #case_type="{ row }">
      <span class="badge" :class="badgeClass(row.case_type)">{{ badgeText(row.case_type) }}</span>
    </template>
    <template #result="{ row }">
      <span class="badge" :class="badgeClass(row.result)">{{ badgeText(row.result) }}</span>
    </template>
    <template #actions="{ row }">
      <div class="actions">
        <button
          v-if="auth.isAdmin && (row.case_type === 'api' || row.case_type === 'ui')"
          class="btn"
          @click="onRerun(row)"
        >再次执行</button>
        <button class="btn secondary" @click="onShowLog(row)">日志</button>
        <button v-if="row.report_path" class="btn secondary" @click="openProtectedFile(`/api/test-records/${row.id}/report`)">报告</button>
        <button v-if="row.screenshot" class="btn secondary" @click="openProtectedFile(`/api/test-records/${row.id}/screenshot`)">截图</button>
      </div>
    </template>
  </AppTable>

  <!-- 分页：对齐旧应用 renderRecords 分页结构 -->
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
  </WorkbenchPanel>

  <BaseModal :open="logVisible" :title="logTitle" @update:open="!$event && closeLog()">
    <div class="v2-records__log" v-html="logBodyHtml"></div>
  </BaseModal>

  <AppFormDialog
    :visible="rerunVisible"
    :title="rerunTitle"
    :fields="rerunFields"
    :values="rerunValues"
    submit-label="提交执行"
    @close="closeRerun"
    @submit="submitRerun"
  />

  <Teleport to="body">
    <div v-if="factoryRerunRecordId" class="v2-records__factory-rerun">
      <iframe
        :key="`${factoryRerunGeneration}-${factoryRerunRecordId}`"
        ref="factoryRerunFrame"
        class="v2-records__factory-rerun-frame"
        title="数据脚本再次执行"
        src="/?v3_embed=1#/dataScripts"
        @load="onFactoryRerunLoad"
      />
    </div>
  </Teleport>
  </div>
</template>

<script setup>
/**
 * Records 视图 — 迁移自旧应用 renderRecords()
 *
 * 对齐项：
 * - 列表：recordColumns（ID/类型/用例ID/结果/执行时间/操作）
 * - 筛选：项目筛选 + 类型筛选（与旧系统一致，无文本搜索框）
 * - 分页：上一页/下一页 + 页码按钮 + 首尾省略号
 * - 日志：showLog（结构化摘要 + 原始日志 + 智能体记录特殊处理）
 * - 下载：openProtectedFile（报告/截图，blob URL 新窗口打开）
 * - 再次执行：当前页弹窗回填。api/ui 走记录确认接口；data_script 复用数据工厂同一套执行表单
 * - 权限：再次执行仅管理员可用，其余查看操作需登录
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import AppTable from '../components/AppTable.vue'
import AppFormDialog from '../components/AppFormDialog.vue'
import { BaseModal } from '../components/v2/base/index.js'
import { WorkbenchPageHeader, WorkbenchPanel } from '../components/v2/workbench/index.js'
import { badgeText, badgeClass } from '../utils/badge.js'
import { buildLogContent } from '../utils/recordLog.js'
import * as recordsApi from '../api/modules/records.js'
import { listEnvs } from '../api/modules/envs.js'

const auth = useAuthStore()
const appStore = useAppStore()
const toast = useToastStore()

// ========== 状态 ==========
const projects = ref([])
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

// 筛选（对齐旧应用 state.filters.recordProjectId / recordType / recordPage）
const filterProjectId = ref(appStore.filters.projectId || '')
const filterType = ref(appStore.filters.recordType || '')

// ========== 列定义 ==========
const recordColumns = [
  { key: 'id', label: 'ID' },
  { key: 'case_type', label: '类型', slot: 'case_type' },
  { key: 'case_id', label: '用例ID' },
  { key: 'result', label: '结果', slot: 'result' },
  { key: 'execute_time', label: '执行时间' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

// ========== 分页计算 ==========
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// 页码按钮列表（对齐旧应用：当前页前后各 2 页 + 首尾省略号）
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

// ========== 数据加载 ==========
async function loadRecords() {
  loading.value = true
  try {
    const resp = await recordsApi.listRecords({
      caseType: filterType.value,
      projectId: filterProjectId.value,
      page: page.value,
      pageSize,
    })
    rows.value = resp.items || []
    total.value = resp.total ?? rows.value.length
    // 对齐旧应用：页码越界时回到最后一页
    const tp = Math.max(1, Math.ceil(total.value / pageSize))
    if (page.value > tp) {
      page.value = tp
      await loadRecords()
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
  page.value = 1
  await loadRecords()
}

async function onTypeChange(event) {
  filterType.value = event.target.value
  appStore.filters.recordType = filterType.value
  page.value = 1
  await loadRecords()
}

// ========== 分页切换 ==========
async function goPage(target) {
  if (target === 'prev') {
    page.value = Math.max(1, page.value - 1)
  } else if (target === 'next') {
    page.value = Math.min(totalPages.value, page.value + 1)
  } else {
    page.value = Number(target)
  }
  await loadRecords()
}

// ========== 日志弹窗 ==========
const logVisible = ref(false)
const logTitle = ref('')
const logBodyHtml = ref('')

async function onShowLog(item) {
  logTitle.value = '加载中...'
  logBodyHtml.value = '<div class="empty">正在解析日志...</div>'
  logVisible.value = true
  try {
    const { title, bodyHtml } = await buildLogContent(item)
    logTitle.value = title
    logBodyHtml.value = bodyHtml
  } catch (error) {
    logTitle.value = `执行日志 #${item.id}`
    logBodyHtml.value = `<pre class="log-view">${String(item.log || '')}</pre>`
  }
}

function closeLog() {
  logVisible.value = false
}

// ========== 下载文件（对齐旧应用 openProtectedFile） ==========
async function openProtectedFile(path) {
  try {
    const response = await fetch(path, {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    if (!response.ok) {
      toast.show('文件不存在或无权访问')
      return
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener,noreferrer')
  } catch (error) {
    toast.show('文件不存在或无权访问')
  }
}

// ========== 再次执行（回填上次上下文并允许修改） ==========
const rerunVisible = ref(false)
const rerunningItem = ref(null)
const rerunContext = ref(null)
const rerunValues = ref({})
const rerunEnvs = ref([])
const rerunTitle = computed(() => '提交执行')
const rerunFields = computed(() => {
  const fields = []
  if (rerunContext.value?.kind === 'api_case') {
    fields.push({
      name: 'env_id',
      label: '执行环境',
      type: 'select',
      options: rerunEnvs.value.map((env) => ({ value: env.id, label: env.env_name })),
      required: true,
    })
  }
  fields.push({
    name: 'variables',
    label: '运行时变量 JSON',
    type: 'textarea',
    rows: 8,
    help: rerunContext.value?.sensitive_keys?.length
      ? `敏感参数 ${rerunContext.value.sensitive_keys.join('、')} 已安全保留；如需替换，请在 JSON 中填写同名字段。`
      : '',
  })
  return fields
})

const FACTORY_RERUN_STYLE_ID = 'v3-rerun-form-style'
const FACTORY_RERUN_STYLE = `
html.v3-embed,
html.v3-embed body {
  height: 100%;
  overflow: hidden;
  background: transparent !important;
}
html.v3-embed body::before {
  display: none !important;
}
html.v3-embed .sidebar,
html.v3-embed .topbar {
  display: none !important;
}
html.v3-embed .modal::backdrop,
html.v3-embed #modal::backdrop {
  background: transparent !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
html.v3-embed.v3-rerun-form-only #app {
  visibility: hidden !important;
  pointer-events: none !important;
}
html.v3-embed.v3-rerun-form-only .modal,
html.v3-embed.v3-rerun-form-only #modal,
html.v3-embed.v3-rerun-form-only #toast {
  visibility: visible !important;
  pointer-events: auto !important;
}
`
const factoryRerunFrame = ref(null)
const factoryRerunRecordId = ref('')
const factoryRerunGeneration = ref(0)
const factoryRerunOpeningId = ref('')
const factoryRerunOpenedId = ref('')

function waitForRerunModule(frameWindow, attempts = 30) {
  return new Promise((resolve, reject) => {
    let remaining = attempts
    const check = () => {
      if (frameWindow?.TestRecordRerun?.open && typeof frameWindow.openRunScriptForm === 'function') {
        resolve(frameWindow.TestRecordRerun)
        return
      }
      remaining -= 1
      if (remaining <= 0) {
        reject(new Error('TestRecordRerun module unavailable'))
        return
      }
      window.setTimeout(check, 100)
    }
    check()
  })
}

function applyFactoryRerunChrome(doc) {
  if (!doc?.documentElement) return
  doc.documentElement.classList.add('v3-embed', 'v3-rerun-form-only')
  if (doc.getElementById(FACTORY_RERUN_STYLE_ID)) return
  const style = doc.createElement('style')
  style.id = FACTORY_RERUN_STYLE_ID
  style.textContent = FACTORY_RERUN_STYLE
  doc.head?.appendChild(style)
}

function isCurrentFactoryRerun(task) {
  return factoryRerunGeneration.value === task.generation
    && String(factoryRerunRecordId.value || '') === task.recordId
}

function closeFactoryRerun(options = {}) {
  factoryRerunGeneration.value += 1
  factoryRerunRecordId.value = ''
  factoryRerunOpeningId.value = ''
  factoryRerunOpenedId.value = ''
  if (options.refresh) loadRecords()
}

function onFactoryModalClose(event) {
  const recordId = event?.currentTarget?.dataset?.factoryRerunId || factoryRerunRecordId.value
  if (!recordId || factoryRerunOpenedId.value !== String(recordId)) return
  closeFactoryRerun({ refresh: true })
}

async function onFactoryRerunLoad(event) {
  const recordId = String(factoryRerunRecordId.value || '').trim()
  const frameEl = event?.target || factoryRerunFrame.value
  const frameWindow = frameEl?.contentWindow
  const doc = frameEl?.contentDocument
  if (!recordId || !frameWindow || !doc) return
  if (factoryRerunOpenedId.value === recordId || factoryRerunOpeningId.value === recordId) return
  factoryRerunOpeningId.value = recordId
  const task = {
    generation: factoryRerunGeneration.value,
    recordId,
    frameWindow,
  }
  try {
    applyFactoryRerunChrome(doc)
    if (doc.querySelector('#loginForm')) {
      throw new Error('登录已失效，请重新登录后再再次执行')
    }
    const modal = doc.getElementById('modal')
    if (modal && modal.dataset.factoryRerunBound !== recordId) {
      modal.dataset.factoryRerunId = recordId
      modal.dataset.factoryRerunBound = recordId
      modal.addEventListener('close', onFactoryModalClose)
    }
    const rerunModule = await waitForRerunModule(task.frameWindow)
    if (!isCurrentFactoryRerun(task)) return
    await rerunModule.open(Number(recordId))
    if (!isCurrentFactoryRerun(task)) return
    if (!modal?.open) {
      toast.show('未找到对应数据脚本入口，请到数据工厂中执行')
      closeFactoryRerun()
      return
    }
    factoryRerunOpenedId.value = recordId
  } catch (error) {
    if (isCurrentFactoryRerun(task)) {
      toast.show(error.message || '数据工厂执行表单加载失败，请刷新后重试')
      closeFactoryRerun()
    }
  } finally {
    if (factoryRerunGeneration.value === task.generation && factoryRerunOpeningId.value === recordId) {
      factoryRerunOpeningId.value = ''
    }
  }
}

async function onRerun(item) {
  try {
    const context = await recordsApi.getReexecuteContext(item.id)
    if (!context?.available) {
      toast.show(context?.message || '该记录缺少完整参数，请从原入口执行')
      return
    }
    if (context.kind === 'data_script') {
      if (!context.script_key) {
        toast.show('该记录缺少脚本类型，请从数据工厂执行')
        return
      }
      closeRerun()
      factoryRerunGeneration.value += 1
      factoryRerunOpenedId.value = ''
      factoryRerunOpeningId.value = ''
      factoryRerunRecordId.value = String(item.id)
      return
    }
    rerunningItem.value = item
    rerunContext.value = context
    rerunEnvs.value = context.kind === 'api_case'
      ? await listEnvs(context.project_id)
      : []
    rerunValues.value = {
      env_id: context.env_id || '',
      variables: JSON.stringify(context.variables || {}, null, 2),
    }
    rerunVisible.value = true
  } catch (error) {
    toast.show(error.message || '加载再次执行参数失败')
  }
}

function closeRerun() {
  rerunVisible.value = false
  rerunningItem.value = null
  rerunContext.value = null
  rerunEnvs.value = []
}

async function submitRerun(data) {
  try {
    const variables = parseJsonObject(data.variables)
    toast.show('正在执行，请稍候')
    const payload = { variables }
    if (rerunContext.value?.kind === 'api_case') payload.env_id = Number(data.env_id)
    const result = await recordsApi.confirmReexecute(rerunningItem.value.id, payload)
    toast.show(`执行完成：${result.result === 'passed' ? '成功' : '失败'}`)
    closeRerun()
    await loadRecords()
  } catch (error) {
    toast.show(error.message || '再次执行失败')
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
  // 加载项目列表（用于筛选下拉框）
  projects.value = await appStore.fetchProjects()
  await loadRecords()
})

onBeforeUnmount(() => {
  closeFactoryRerun()
})
</script>

<style scoped>
.v2-records {
  display: grid;
  gap: 12px;
  width: 100%;
  max-width: none;
  margin: 0;
}

.v2-records__factory-rerun {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: transparent;
}

.v2-records__factory-rerun-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: transparent;
  color-scheme: none;
}

.v2-records :deep(.v2-workbench-page-header__eyebrow) {
  color: #64748b;
  font-size: 11px;
  letter-spacing: 0.1em;
}

.v2-records :deep(.v2-workbench-page-header__title) {
  font-size: 26px;
  font-weight: 650;
  line-height: 1.25;
}

.v2-records :deep(.v2-workbench-panel) {
  min-width: 0;
  gap: 10px;
}

.v2-records :deep(.v2-workbench-panel__header) {
  min-height: 0;
  padding: 0 2px;
}

.v2-records :deep(.v2-workbench-panel__body) {
  display: flex;
  min-height: calc(100vh - 200px);
  flex-direction: column;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
}

.v2-records :deep(.v2-base-empty-state) {
  min-height: 180px;
  justify-content: center;
}

.v2-records :deep(.v2-base-empty-state__icon) {
  width: 56px;
  height: 56px;
  color: #94a3b8;
  background: #f1f5f9;
}

.v2-records :deep(.v2-app-table) {
  flex: 1 1 auto;
}

.v2-records :deep(.v2-app-table__header) {
  height: 40px;
  padding: 0 12px;
  font-size: 11px;
}

.v2-records :deep(.v2-app-table__cell) {
  height: 44px;
  padding: 0 12px;
  font-size: 13px;
}

.toolbar,
.filters,
.actions,
.pagination,
.page-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.toolbar,
.pagination {
  justify-content: space-between;
  padding: 12px 16px;
}

.toolbar {
  border-bottom: 1px solid var(--v2-border-panel);
  background: #ffffff;
}

.pagination {
  border-top: 1px solid var(--v2-border-panel);
  background: #ffffff;
}

.field {
  display: grid;
  gap: 4px;
}

.field label,
.page-info {
  color: var(--v2-text-muted);
  font-size: 11px;
  font-weight: 500;
}

select,
.btn {
  min-height: 32px;
  border: 1px solid var(--v2-border-default);
  border-radius: 6px;
  background: #ffffff;
  color: var(--v2-text-secondary);
  font: inherit;
  font-size: 12px;
}

select {
  min-width: 140px;
  padding: 0 10px;
}

.btn {
  padding: 0 12px;
  cursor: pointer;
  font-weight: 500;
}

.btn:not(.secondary) {
  border-color: var(--v2-action-primary);
  background: var(--v2-action-primary);
  color: var(--v2-text-inverse);
}

.btn.active {
  border-color: var(--v2-action-primary);
  background: var(--v2-action-primary-soft);
  color: var(--v2-action-primary);
}

.btn:focus-visible,
select:focus-visible {
  outline: 0;
  box-shadow: var(--v2-state-focus-ring);
}

.badge {
  display: inline-flex;
  min-height: 22px;
  align-items: center;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--v2-surface-soft);
  color: var(--v2-text-secondary);
  font-size: 10px;
  font-weight: 600;
}

.badge.ok {
  background: var(--v2-feedback-success-soft);
  color: var(--v2-feedback-success);
}

.badge.fail {
  background: var(--v2-feedback-danger-soft);
  color: var(--v2-feedback-danger);
}

.v2-records__log {
  max-height: calc(var(--v2-space-7) * 7);
  overflow: auto;
  color: var(--v2-text-secondary);
  font-size: 12px;
}

.v2-records__log :deep(pre) {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--v2-border-panel);
  border-radius: 8px;
  background: var(--v2-surface-workspace);
  font-family: var(--v2-font-family-mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
