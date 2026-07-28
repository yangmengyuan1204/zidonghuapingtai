/**
 * Dashboard API 模块
 *
 * 对齐旧应用 app.js renderDashboard 中的接口调用：
 *   GET /api/dashboard?project_id=xxx
 *
 * 后端返回数据结构（与旧应用完全一致）：
 *   {
 *     project_count: number,
 *     env_count: number,
 *     api_case_count: number,
 *     ui_case_count: number,
 *     record_count: number,
 *     latest_records: Array<{
 *       id: number,
 *       case_type: string,  // 'api' | 'ui' | ...
 *       case_id: number,
 *       result: string,     // 'passed' | 'failed' | ...
 *       execute_time: string,
 *       report_path?: string,
 *       screenshot?: string,
 *       log?: string,
 *     }>
 *   }
 */
import { api } from '../client.js'

/**
 * 获取 Dashboard 数据
 * @param {string} [projectId] - 项目 ID（空字符串表示全部）
 * @returns {Promise<object>}
 */
export function getDashboard(projectId) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return api(`/api/dashboard${query}`)
}
