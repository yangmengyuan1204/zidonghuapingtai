/**
 * Ui Cases API 模块
 * 对齐旧应用 /api/ui-cases + /api/ui-executions + /api/ui-record 接口调用
 *
 * 后端：app/routers/ui_cases.py
 *   - GET    /api/ui-cases                       列表（支持 project_id 过滤）
 *   - POST   /api/ui-cases                       新增（require_admin）
 *   - PUT    /api/ui-cases/{id}                  更新（require_admin）
 *   - DELETE /api/ui-cases/{id}                  删除（require_admin）
 *   - POST   /api/ui-cases/{id}/execute          单条执行（同步）
 *   - POST   /api/ui-cases/{id}/visual-execute   可视化执行（异步 + 轮询）
 *   - GET    /api/ui-executions/{run_id}         查询可视化执行状态
 *   - POST   /api/ui-cases/{id}/heal-steps       接受 healing 建议更新 locator
 *
 * 后端：app/routers/ui_record.py（录制UI用例）
 *   - POST   /api/ui-record/sessions             启动录制会话
 *   - GET    /api/ui-record/sessions/{id}/events 查询录制事件（轮询）
 *   - DELETE /api/ui-record/sessions/{id}        取消录制
 *   - POST   /api/ui-record/sessions/{id}/save   保存录制为 UI 用例
 */
import { api } from '../client.js'

export function listUiCases(projectId) {
  const qs = projectId ? `?project_id=${projectId}` : ''
  return api(`/api/ui-cases${qs}`)
}

export function createUiCase(data) {
  return api('/api/ui-cases', { method: 'POST', body: data })
}

export function updateUiCase(id, data) {
  return api(`/api/ui-cases/${id}`, { method: 'PUT', body: data })
}

export function deleteUiCase(id) {
  return api(`/api/ui-cases/${id}`, { method: 'DELETE' })
}

export function executeUiCase(id, body = {}) {
  return api(`/api/ui-cases/${id}/execute`, { method: 'POST', body })
}

export function visualExecuteUiCase(id, body = {}) {
  return api(`/api/ui-cases/${id}/visual-execute`, { method: 'POST', body })
}

export function getUiExecution(runId) {
  return api(`/api/ui-executions/${runId}`)
}

export function healUiCaseSteps(id, healMap) {
  return api(`/api/ui-cases/${id}/heal-steps`, { method: 'POST', body: { heal_map: healMap } })
}

// ========== 录制UI用例 API（对齐旧应用 /api/ui-record/sessions/*） ==========
export function startUiRecordSession(data) {
  return api('/api/ui-record/sessions', { method: 'POST', body: data })
}

export function getUiRecordEvents(sessionId) {
  return api(`/api/ui-record/sessions/${sessionId}/events`)
}

export function cancelUiRecordSession(sessionId) {
  return api(`/api/ui-record/sessions/${sessionId}`, { method: 'DELETE' })
}

export function saveUiRecordSession(sessionId, data) {
  return api(`/api/ui-record/sessions/${sessionId}/save`, { method: 'POST', body: data })
}

export function startUiRecordPreflight(sessionId, data = {}) {
  return api(`/api/ui-record/sessions/${sessionId}/preflight`, { method: 'POST', body: data })
}

export function getUiRecordPreflight(runId) {
  return api(`/api/ui-record/preflights/${runId}`)
}

export function applyUiRecordLocator(sessionId, stepIndex, locator) {
  return api(`/api/ui-record/sessions/${sessionId}/steps/${stepIndex}/locator`, {
    method: 'POST',
    body: { locator },
  })
}

export function listUiCaseRevisions(caseId) {
  return api(`/api/ui-cases/${caseId}/revisions`)
}

export function rollbackUiCaseRevision(caseId, revisionId) {
  return api(`/api/ui-cases/${caseId}/revisions/${revisionId}/rollback`, { method: 'POST' })
}

// ========== 录制验证（双轮预检 + 重新选点 + 重启） ==========
export function getUiRecordProjectConfig(projectId) {
  return api(`/api/ui-record/projects/${projectId}/config`)
}

export function saveUiRecordProjectConfig(projectId, data) {
  return api(`/api/ui-record/projects/${projectId}/config`, { method: 'PUT', body: data })
}

export function startUiRecordRepick(runId, stepIndex) {
  return api(`/api/ui-record/preflights/${runId}/steps/${stepIndex}/repick/start`, { method: 'POST' })
}

export function restartUiRecordPreflight(runId) {
  return api(`/api/ui-record/preflights/${runId}/restart`, { method: 'POST' })
}
