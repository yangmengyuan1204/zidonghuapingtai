/**
 * Test Records API 模块
 * 对齐旧应用 /api/test-records 接口调用
 *
 * 后端：app/routers/test_records.py
 *   - GET    /api/test-records                       列表（支持 case_type / project_id / page / page_size）
 *   - GET    /api/test-records/{id}                  详情
 *   - GET    /api/test-records/{id}/report           下载报告文件
 *   - GET    /api/test-records/{id}/screenshot       下载截图文件
 *   - GET    /api/test-records/{id}/re-execute       获取再次执行上下文
 *   - POST   /api/test-records/{id}/re-execute       确认再次执行
 */
import { api } from '../client.js'

export function listRecords(params = {}) {
  const qs = new URLSearchParams()
  if (params.caseType) qs.set('case_type', params.caseType)
  if (params.projectId) qs.set('project_id', params.projectId)
  if (params.page) qs.set('page', params.page)
  if (params.pageSize) qs.set('page_size', params.pageSize)
  const query = qs.toString()
  return api(`/api/test-records${query ? `?${query}` : ''}`)
}

export function getRecord(id) {
  return api(`/api/test-records/${id}`)
}

export function getReexecuteContext(id) {
  return api(`/api/test-records/${id}/re-execute`)
}

export function confirmReexecute(id, overrides = {}) {
  return api(`/api/test-records/${id}/re-execute`, {
    method: 'POST',
    body: { confirmed: true, ...overrides },
  })
}
