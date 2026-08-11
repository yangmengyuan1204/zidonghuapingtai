import { api } from '../client.js'

const base = '/api/system-regression'
export function listCases() { return api(`${base}/suites/japan/cases`) }
export function updateCase(id, payload) { return api(`${base}/cases/${id}`, { method: 'PATCH', body: payload }) }
export function copyCase(id) { return api(`${base}/cases/${id}/copy`, { method: 'POST' }) }
export function resetCase(id) { return api(`${base}/cases/${id}/reset`, { method: 'POST' }) }
export function createBatch(payload) { return api(`${base}/batches`, { method: 'POST', body: payload }) }
export function getBatch(id) { return api(`${base}/batches/${id}`) }
export function stopBatch(id) { return api(`${base}/batches/${id}/stop`, { method: 'POST' }) }
export function rerunCase(id) { return api(`${base}/runs/${id}/rerun`, { method: 'POST' }) }
export function resumeAccount(id, payload) { return api(`${base}/runs/${id}/resume-account`, { method: 'POST', body: payload }) }
