<template>
  <div class="v2-dashboard">
    <WorkbenchPageHeader
      eyebrow="TEST OPERATIONS"
      title="质量运行概览"
      description="基于当前项目的真实用例与执行记录，集中查看质量状态、趋势和待处理事项。"
    >
      <template #actions>
        <BaseDropdown
          v-model:open="projectDropdownOpen"
          aria-label="选择项目"
          menu-label="项目列表"
          match-trigger-width
          @select="onProjectChange"
        >
          <template #trigger>
            <BaseButton class="v2-dashboard__project-trigger" variant="secondary">
              <span>{{ selectedProjectLabel }}</span>
              <span aria-hidden="true">⌄</span>
            </BaseButton>
          </template>
          <BaseDropdownItem value="">全部项目</BaseDropdownItem>
          <BaseDropdownItem v-for="project in projects" :key="project.id" :value="String(project.id)">
            {{ project.name }}
          </BaseDropdownItem>
        </BaseDropdown>
        <BaseButton @click="navigateToView('records')">查看执行报告</BaseButton>
      </template>
    </WorkbenchPageHeader>

    <div v-if="loading" class="v2-dashboard__loading" aria-label="正在加载质量概览">
      <BaseSkeleton variant="rectangle" />
      <BaseSkeleton variant="rectangle" />
      <BaseSkeleton :lines="5" />
    </div>

    <BaseErrorState
      v-else-if="errorMessage"
      title="质量概览加载失败"
      :message="errorMessage"
      action-label="重新加载"
      @action="loadDashboard"
    />

    <template v-else>
      <WorkbenchMetricRail
        :status-label="statusSummary.label"
        :status-title="statusSummary.title"
        :status-detail="statusSummary.detail"
        :items="metricItems"
      />

      <div class="v2-dashboard__overview-grid">
        <WorkbenchPanel title="执行趋势" :subtitle="trendSubtitle">
          <template #actions>
            <WorkbenchStatus :tone="statusSummary.tone" :label="statusSummary.rateLabel" compact />
          </template>
          <WorkbenchTrendChart
            :labels="trendData.labels"
            :passed="trendData.passed"
            :failed="trendData.failed"
          />
        </WorkbenchPanel>

        <WorkbenchPanel title="需要关注" subtitle="仅显示可由当前数据证明的事项">
          <WorkbenchAttentionList :items="attentionItems" @action="handleAttentionAction" />
        </WorkbenchPanel>
      </div>

      <WorkbenchPanel title="最近执行" subtitle="保留日志、报告和截图入口">
        <template #actions>
          <BaseButton variant="ghost" size="compact" @click="navigateToView('records')">全部记录</BaseButton>
        </template>
        <BaseEmptyState
          v-if="!(data.latest_records || []).length"
          title="暂无执行记录"
          description="执行接口或 UI 用例后，最新结果会显示在这里。"
          compact
          icon-hidden
        />
        <AppTable v-else :columns="columns" :rows="data.latest_records">
          <template #case_type="{ row }">
            <BaseBadge :tone="badgeTone(row.case_type)">{{ badgeText(row.case_type) }}</BaseBadge>
          </template>
          <template #result="{ row }">
            <BaseBadge :tone="badgeTone(row.result)">{{ badgeText(row.result) }}</BaseBadge>
          </template>
          <template #actions="{ row }">
            <div class="v2-dashboard__actions">
              <BaseButton variant="secondary" size="compact" @click="showLog(row)">日志</BaseButton>
              <BaseButton v-if="row.report_path" variant="secondary" size="compact" @click="openProtectedFile(`/api/test-records/${row.id}/report`)">报告</BaseButton>
              <BaseButton v-if="row.screenshot" variant="secondary" size="compact" @click="openProtectedFile(`/api/test-records/${row.id}/screenshot`)">截图</BaseButton>
            </div>
          </template>
        </AppTable>
      </WorkbenchPanel>
    </template>

    <BaseModal v-model:open="logModalOpen" title="执行日志">
      <pre class="v2-dashboard__log">{{ activeLog }}</pre>
    </BaseModal>
  </div>
</template>

<script setup>
/**
 * Dashboard 视图
 * 对齐旧应用 app.js renderDashboard：
 * - 项目下拉筛选（共享 localStorage 'projectId'）
 * - 5 个统计卡片
 * - 最近执行表格（recordColumns，无 showRerun）
 *
 * 依赖公共基础设施：
 * - AppTable（通用表格组件）
 * - app store（项目筛选 + 项目缓存）
 * - axios client（API 调用）
 * - badge 工具（与旧应用 badge() 一致）
 *
 * 接口调用与旧应用完全一致：
 * - GET /api/projects（项目列表，缓存）
 * - GET /api/dashboard?project_id=xxx
 *
 * actions 按钮行为与旧应用一致：
 * - 日志/报告/截图：跳回旧应用 records 页面（Records 未迁移，Phase 2B 处理）
 */
import { computed, ref, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { navigateToView } from '../services/navigation.js'
import { getDashboard } from '../api/modules/dashboard.js'
import { listRecords } from '../api/modules/records.js'
import { badgeText, badgeClass } from '../utils/badge.js'
import { api } from '../api/client.js'
import AppTable from '../components/AppTable.vue'
import {
  BaseBadge,
  BaseButton,
  BaseDropdown,
  BaseDropdownItem,
  BaseEmptyState,
  BaseErrorState,
  BaseModal,
  BaseSkeleton,
} from '../components/v2/base/index.js'
import {
  WorkbenchAttentionList,
  WorkbenchMetricRail,
  WorkbenchPageHeader,
  WorkbenchPanel,
  WorkbenchStatus,
  WorkbenchTrendChart,
} from '../components/v2/workbench/index.js'

const app = useAppStore()

const projects = ref([])
const loading = ref(false)
const errorMessage = ref('')
const projectDropdownOpen = ref(false)
const records = ref([])
const logModalOpen = ref(false)
const activeLog = ref('')
const data = ref({
  project_count: 0,
  env_count: 0,
  api_case_count: 0,
  ui_case_count: 0,
  record_count: 0,
  latest_records: [],
})
const selectedProjectLabel = computed(() => {
  const selectedId = String(app.filters.projectId || '')
  if (!selectedId) return '全部'
  return projects.value.find((project) => String(project.id) === selectedId)?.name || '全部'
})
const failedRecords = computed(() => records.value.filter((record) => isFailedResult(record.result)))
const metricItems = computed(() => [
  { key: 'projects', label: '项目', value: data.value.project_count, trend: selectedProjectLabel.value },
  { key: 'envs', label: '环境', value: data.value.env_count, trend: data.value.env_count ? '可用于执行' : '尚未配置', tone: data.value.env_count ? 'success' : 'warning' },
  { key: 'apiCases', label: '接口用例', value: data.value.api_case_count, trend: '测试资产' },
  { key: 'uiCases', label: 'UI 用例', value: data.value.ui_case_count, trend: data.value.ui_case_count ? '浏览器资产' : '尚未创建', tone: data.value.ui_case_count ? 'info' : 'warning' },
  { key: 'records', label: '执行记录', value: data.value.record_count, trend: `${failedRecords.value.length} 条失败待查`, tone: failedRecords.value.length ? 'danger' : 'success' },
])

const trendData = computed(() => {
  const days = new Map()
  for (const record of records.value) {
    const dateKey = String(record.execute_time || '').slice(0, 10)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) continue
    const bucket = days.get(dateKey) || { passed: 0, failed: 0 }
    if (isPassedResult(record.result)) bucket.passed += 1
    else if (isFailedResult(record.result)) bucket.failed += 1
    days.set(dateKey, bucket)
  }
  const dateKeys = [...days.keys()].sort().slice(-7)
  return {
    labels: dateKeys.map((date) => date.slice(5)),
    passed: dateKeys.map((date) => days.get(date).passed),
    failed: dateKeys.map((date) => days.get(date).failed),
  }
})

const trendSubtitle = computed(() => trendData.value.labels.length
  ? `真实记录覆盖 ${trendData.value.labels.length} 个执行日`
  : '当前筛选范围内暂无可聚合记录')
const statusSummary = computed(() => {
  const passed = trendData.value.passed.reduce((sum, value) => sum + value, 0)
  const failed = trendData.value.failed.reduce((sum, value) => sum + value, 0)
  const total = passed + failed
  const rate = total ? Math.round((passed / total) * 100) : 0
  if (failed) {
    return { label: 'QUALITY STATUS', title: '存在失败待处理', detail: `${failed} 条失败记录进入关注队列`, tone: 'warning', rateLabel: `通过率 ${rate}%` }
  }
  if (total) {
    return { label: 'QUALITY STATUS', title: '运行稳定', detail: `已聚合 ${total} 条真实执行结果`, tone: 'success', rateLabel: `通过率 ${rate}%` }
  }
  return { label: 'QUALITY STATUS', title: '等待首次执行', detail: '当前范围内暂无执行结果', tone: 'neutral', rateLabel: '暂无样本' }
})
const attentionItems = computed(() => {
  const items = failedRecords.value.slice(0, 3).map((record) => ({
    id: `record:${record.id}`,
    tone: 'danger',
    title: `执行记录 #${record.id} 失败`,
    detail: `${badgeText(record.case_type)} · ${record.execute_time || '时间未知'}`,
    actionLabel: '查看日志',
  }))
  if (Number(data.value.env_count) === 0) {
    items.push({ id: 'route:projects', tone: 'warning', title: '当前范围尚未配置环境', detail: '测试执行需要至少一个可用环境', actionLabel: '配置环境' })
  }
  if (Number(data.value.ui_case_count) === 0) {
    items.push({ id: 'route:uiCases', tone: 'info', title: '当前范围尚无 UI 用例', detail: '创建用例后可进行浏览器自动化执行', actionLabel: '创建用例' })
  }
  return items.slice(0, 5)
})

// 表格列定义（对齐旧应用 recordColumns()，showRerun=false）
const columns = [
  { key: 'id', label: 'ID' },
  { key: 'case_type', label: '类型', slot: 'case_type' },
  { key: 'case_id', label: '用例ID' },
  { key: 'result', label: '结果', slot: 'result' },
  { key: 'execute_time', label: '执行时间' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

async function loadDashboard() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [projectList, dashboardData, recordResponse] = await Promise.all([
      app.fetchProjects(),
      getDashboard(app.filters.projectId),
      listRecords({ projectId: app.filters.projectId, page: 1, pageSize: 200 }),
    ])
    projects.value = projectList
    data.value = dashboardData
    records.value = Array.isArray(recordResponse) ? recordResponse : (recordResponse.items || [])
  } catch (error) {
    errorMessage.value = error?.message || '请稍后重试'
  } finally {
    loading.value = false
  }
}

async function onProjectChange(projectId) {
  app.setProjectId(String(projectId || ''))
  await loadDashboard()
}

function badgeTone(value) {
  return {
    ok: 'success',
    fail: 'danger',
    warn: 'warning',
  }[badgeClass(value)] || 'neutral'
}

function isPassedResult(value) {
  return ['passed', 'pass', 'success', 'ok'].includes(String(value || '').toLowerCase())
}

function isFailedResult(value) {
  return ['failed', 'fail', 'error'].includes(String(value || '').toLowerCase())
}

/**
 * 显示执行日志
 *
 * 旧应用 showLog(item) 是复杂逻辑（含智能体记录处理），
 * 属于 Records 模块功能。Records 未迁移（Phase 2B 处理），
 * 本轮跳回旧应用 records 页面查看。
 *
 * TODO: Records 页面迁移完成后恢复旧系统的结构化日志 Modal
 *       （含智能体记录 summary/variables 解析与展示）
 */
function showLog(row) {
  const raw = row?.log || '该记录没有可显示的日志。'
  try {
    activeLog.value = JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    activeLog.value = String(raw)
  }
  logModalOpen.value = true
}

function handleAttentionAction(id) {
  const [kind, value] = String(id).split(':')
  if (kind === 'route') {
    navigateToView(value)
    return
  }
  if (kind === 'record') {
    const record = records.value.find((item) => String(item.id) === value)
    if (record) showLog(record)
  }
}

/**
 * 打开受保护文件（报告/截图）
 *
 * 对齐旧应用 openProtectedFile(path)：
 * fetch 带 JWT → blob → window.open
 *
 * 错误提示由 axios 响应拦截器统一处理（client.js L60-63），
 * 此处不再重复 toast，避免一次错误弹出两次提示。
 */
async function openProtectedFile(path) {
  try {
    const blob = await api(path, { responseType: 'blob' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener,noreferrer')
  } catch (error) {
    // 错误已由 axios 拦截器 toast，此处仅吞掉，避免双重提示
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.v2-dashboard {
  display: grid;
  gap: 12px;
  width: 100%;
  max-width: none;
  margin: 0;
  padding-bottom: 8px;
}

.v2-dashboard :deep(.v2-workbench-page-header) {
  min-height: auto;
  align-items: flex-start;
  margin-bottom: 0;
}

.v2-dashboard :deep(.v2-workbench-page-header__copy) {
  display: block;
}

.v2-dashboard :deep(.v2-workbench-page-header__eyebrow) {
  margin: 0 0 6px;
  color: #64748b;
  font-size: 11px;
  letter-spacing: 0.1em;
}

.v2-dashboard :deep(.v2-workbench-page-header__title) {
  font-size: 26px;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.v2-dashboard :deep(.v2-workbench-page-header__description) {
  margin-top: 6px;
  color: var(--v2-text-muted);
  font-size: 13px;
}

.v2-dashboard :deep(.v2-workbench-page-header__actions) {
  gap: 8px;
}

.v2-dashboard :deep(.v2-workbench-metric-rail) {
  gap: 12px;
  box-shadow: none;
  border: 0;
  background: transparent;
}

.v2-dashboard :deep(.v2-workbench-metric-rail__items) {
  gap: 12px;
}

.v2-dashboard :deep(.v2-workbench-metric-rail__intro),
.v2-dashboard :deep(.v2-workbench-metric-rail__item) {
  min-height: 88px;
  box-sizing: border-box;
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
}

.v2-dashboard :deep(.v2-workbench-metric-rail__status) {
  font-size: 15px;
  line-height: var(--v2-line-height-tight);
}

.v2-dashboard :deep(.v2-workbench-metric-rail__value) {
  font-size: 22px;
  font-variant-numeric: tabular-nums;
}

.v2-dashboard :deep(.v2-workbench-metric-rail__kicker),
.v2-dashboard :deep(.v2-workbench-metric-rail__label),
.v2-dashboard :deep(.v2-workbench-metric-rail__trend),
.v2-dashboard :deep(.v2-workbench-metric-rail__detail) {
  font-size: var(--v2-font-size-tiny);
  line-height: var(--v2-line-height-caption);
}

.v2-dashboard :deep(.v2-workbench-panel) {
  gap: 10px;
  box-shadow: none;
}

.v2-dashboard :deep(.v2-workbench-panel__header) {
  min-height: 0;
  box-sizing: border-box;
  padding: 0 2px;
}

.v2-dashboard :deep(.v2-workbench-panel__title) {
  font-size: 13px;
  font-weight: 600;
}

.v2-dashboard :deep(.v2-workbench-panel__subtitle) {
  margin-top: 0;
  line-height: var(--v2-line-height-caption);
}

.v2-dashboard :deep(.v2-workbench-panel__body) {
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
}

.v2-dashboard :deep(.v2-base-empty-state) {
  min-height: 180px;
  justify-content: center;
}

.v2-dashboard :deep(.v2-base-empty-state__icon) {
  width: 56px;
  height: 56px;
  color: #94a3b8;
  background: #f1f5f9;
}

.v2-dashboard :deep(.v2-workbench-trend-chart) {
  padding: 12px 16px 16px;
}

.v2-dashboard :deep(.v2-workbench-trend-chart__svg) {
  height: calc(var(--v2-space-7) * 2 + var(--v2-space-6));
  min-height: calc(var(--v2-space-7) * 2 + var(--v2-space-6));
}

.v2-dashboard :deep(.v2-workbench-trend-chart__legend) {
  margin-top: 0;
}

.v2-dashboard :deep(.v2-app-table__header) {
  height: 40px;
  box-sizing: border-box;
  padding: 0 14px;
}

.v2-dashboard :deep(.v2-app-table__cell) {
  height: 44px;
  box-sizing: border-box;
  padding: 8px 14px;
  font-variant-numeric: tabular-nums;
}

.v2-dashboard__loading {
  display: grid;
  gap: 12px;
}

.v2-dashboard__overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 28%);
  gap: 12px;
  align-items: stretch;
}

.v2-dashboard__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 0;
  padding: 12px 16px;
  border-bottom: 1px solid var(--v2-border-panel);
  background: #ffffff;
}

.v2-dashboard__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 12px;
}

.v2-dashboard__project-field {
  min-width: 200px;
  display: grid;
  gap: 4px;
}

.v2-dashboard__project-field > label {
  color: var(--v2-text-secondary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.v2-dashboard__project-trigger {
  width: 100%;
  justify-content: space-between;
}

.v2-dashboard__project-trigger :deep(.v2-base-button__content) {
  width: 100%;
  justify-content: space-between;
}

.v2-dashboard__stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 0;
}

.v2-dashboard__stat-label {
  display: block;
  color: var(--v2-text-muted);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.v2-dashboard__stat-value {
  display: block;
  margin-top: 6px;
  color: var(--v2-action-primary);
  font-size: 20px;
  font-weight: 600;
}

.v2-dashboard__section-header {
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: #ffffff;
  border-bottom: 1px solid var(--v2-border-panel);
}

.v2-dashboard__section-header h3 {
  margin: 0;
  color: var(--v2-text-primary);
  font-size: 13px;
  font-weight: 600;
}

.v2-dashboard__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.v2-dashboard__log {
  max-height: calc(var(--v2-space-7) * 7);
  overflow: auto;
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--v2-border-panel);
  border-radius: 8px;
  background: var(--v2-surface-workspace);
  color: var(--v2-text-secondary);
  font-family: var(--v2-font-family-mono);
  font-size: 12px;
  line-height: var(--v2-line-height-body);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 1080px) {
  .v2-dashboard__overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .v2-dashboard__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .v2-dashboard__stats {
    grid-template-columns: 1fr;
  }
}
</style>
