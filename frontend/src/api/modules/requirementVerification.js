import { api } from '../client.js'

const base = '/api/requirement-verifications'

export function listTasks(params = {}) {
  const query = new URLSearchParams()
  if (params.projectId) query.set('project_id', params.projectId)
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.status) query.set('status', params.status)
  return api(`${base}${query.size ? `?${query}` : ''}`)
}

export function createTask(payload) { return api(base, { method: 'POST', body: payload }) }
export function getTask(id) { return api(`${base}/${id}`) }
export function deleteTask(id) { return api(`${base}/${id}`, { method: 'DELETE' }) }
export function analyzeTask(id) { return api(`${base}/${id}/analyze`, { method: 'POST', body: { mode: 'standard' } }) }
export function preflightTask(id, payload) { return api(`${base}/${id}/preflight`, { method: 'POST', body: payload }) }
export function runTask(id, payload) { return api(`${base}/${id}/runs`, { method: 'POST', body: payload }) }
export function getRun(id) { return api(`${base}/runs/${id}`) }
export function pauseRun(id) { return api(`${base}/runs/${id}/pause`, { method: 'POST' }) }
export function resumeRun(id) { return api(`${base}/runs/${id}/resume`, { method: 'POST' }) }
export function cancelRun(id) { return api(`${base}/runs/${id}/cancel`, { method: 'POST' }) }
