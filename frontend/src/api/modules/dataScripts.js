import { api } from '../client.js'

export function listDataScriptCatalog(projectId) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return api(`/api/requirement-verifications/data-script-catalog${query}`)
}

export function executeDataScript(scriptType, payload) {
  return api(`/api/data-scripts/${scriptType.replaceAll('_', '-')}`, { method: 'POST', body: payload })
}

export function createAgentSession(payload) {
  return api('/api/data-scripts/agent/sessions', { method: 'POST', body: payload })
}

export function getAgentSession(id) {
  return api(`/api/data-scripts/agent/sessions/${id}`)
}

export function sendAgentMessage(id, message) {
  return api(`/api/data-scripts/agent/sessions/${id}/messages`, { method: 'POST', body: { message } })
}

export function confirmAgentSession(id, planVersion) {
  return api(`/api/data-scripts/agent/sessions/${id}/confirm`, { method: 'POST', body: { plan_version: planVersion } })
}

export function confirmAgentRisk(id, payload) {
  return api(`/api/data-scripts/agent/sessions/${id}/risk-confirm`, { method: 'POST', body: payload })
}

export function cancelAgentSession(id) {
  return api(`/api/data-scripts/agent/sessions/${id}/cancel`, { method: 'POST' })
}
