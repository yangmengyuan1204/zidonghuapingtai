<template>
  <div>
    <!-- 项目筛选 -->
    <div class="toolbar">
      <div class="filters">
        <div class="field compact">
          <label>项目</label>
          <select :value="app.filters.projectId" @change="onProjectChange">
            <option value="">全部</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats">
      <div class="stat"><span>项目</span><strong>{{ data.project_count }}</strong></div>
      <div class="stat"><span>环境</span><strong>{{ data.env_count }}</strong></div>
      <div class="stat"><span>接口用例</span><strong>{{ data.api_case_count }}</strong></div>
      <div class="stat"><span>UI用例</span><strong>{{ data.ui_case_count }}</strong></div>
      <div class="stat"><span>执行记录</span><strong>{{ data.record_count }}</strong></div>
    </div>

    <!-- 最近执行 -->
    <div class="panel-title"><h3>最近执行</h3></div>
    <div v-if="loading" class="panel"><div class="empty">加载中...</div></div>
    <AppTable v-else :columns="columns" :rows="data.latest_records || []">
      <template #case_type="{ row }">
        <span class="badge" :class="badgeClass(row.case_type)">{{ badgeText(row.case_type) }}</span>
      </template>
      <template #result="{ row }">
        <span class="badge" :class="badgeClass(row.result)">{{ badgeText(row.result) }}</span>
      </template>
      <template #actions="{ row }">
        <div class="actions">
          <button class="btn secondary" @click="showLog(row)">日志</button>
          <button v-if="row.report_path" class="btn secondary" @click="openProtectedFile(`/api/test-records/${row.id}/report`)">报告</button>
          <button v-if="row.screenshot" class="btn secondary" @click="openProtectedFile(`/api/test-records/${row.id}/screenshot`)">截图</button>
        </div>
      </template>
    </AppTable>
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
import { ref, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useToastStore } from '../stores/toast.js'
import { navigateToView } from '../services/navigation.js'
import { getDashboard } from '../api/modules/dashboard.js'
import { badgeText, badgeClass } from '../utils/badge.js'
import { api } from '../api/client.js'
import AppTable from '../components/AppTable.vue'

const app = useAppStore()
const toast = useToastStore()

const projects = ref([])
const loading = ref(false)
const data = ref({
  project_count: 0,
  env_count: 0,
  api_case_count: 0,
  ui_case_count: 0,
  record_count: 0,
  latest_records: [],
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
  try {
    projects.value = await app.fetchProjects()
    data.value = await getDashboard(app.filters.projectId)
  } catch (error) {
    toast.show(error.message)
  } finally {
    loading.value = false
  }
}

async function onProjectChange(event) {
  app.setProjectId(event.target.value)
  await loadDashboard()
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
  navigateToView('records')
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
/* 使用旧应用 .toolbar / .stats / .stat / .panel-title / .actions / .badge 样式（来自 legacy.css） */
</style>
