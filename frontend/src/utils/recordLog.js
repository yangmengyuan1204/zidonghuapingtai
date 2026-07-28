/**
 * 执行记录日志工具函数
 * 对齐旧应用 app.js renderChineseSummary / showLog 日志解析逻辑
 */

/**
 * 转义 HTML 特殊字符（对齐旧应用 escapeHtml）
 */
export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 解析日志文本为 JSON 对象，失败则返回 null
 * 对齐旧应用 showLog 中的 JSON.parse 逻辑
 */
export function parseLog(rawText) {
  if (!rawText) return null
  try {
    const candidate = JSON.parse(rawText)
    if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) return candidate
  } catch {
    // 非合法 JSON，返回 null
  }
  return null
}

/**
 * 判断是否为 DeepSeek 数据智能体记录
 * 对齐旧应用 showLogWithDataAgentSummary 的判断
 */
export function isDataAgentRecord(parsed) {
  return parsed?.script === 'DeepSeek数据智能体'
}

/**
 * 从解析后的日志中提取结构化汇总数据
 * 对齐旧应用 showLog 中的 summary 提取逻辑
 */
export function extractSummary(parsed) {
  if (!parsed) return null
  if (parsed.summary && typeof parsed.summary === 'object' && Object.keys(parsed.summary).length > 0) {
    return parsed.summary
  }
  if (parsed.variables && typeof parsed.variables === 'object' && Object.keys(parsed.variables).length > 0) {
    return parsed.variables
  }
  if (parsed && typeof parsed === 'object' && Object.keys(parsed).length > 0) {
    const metaKeys = ['script', 'mode', 'started_at', 'finished_at', 'duration_ms', 'steps', 'batches', 'shops', 'login', 'backend', 'backend_porder', '_runtime']
    const hasMeta = metaKeys.some((k) => k in parsed)
    if (!hasMeta) return parsed
  }
  return null
}

/**
 * 渲染中文汇总表格
 * 对齐旧应用 app.js renderChineseSummary(summary)
 *
 * 完整迁移 LABEL_MAP / BOOL_TRUE_TEXT / 表格+数组+对象分组渲染逻辑
 */
const LABEL_MAP = {
  keyword: '搜索关键词',
  expected_total: '期望添加商品数',
  available_expected_total: '可用期望商品数',
  added_total: '实际添加商品数',
  shop_types: '商品来源',
  skipped_shop_types: '跳过的来源',
  failed_shop_types: '失败的来源',
  strict_shop_count: '严格店铺数',
  reason: '失败原因',
  ready_shops: '已就绪店铺数',
  target_shops: '目标店铺数',
  per_shop: '每店商品数',
  api_added_total: 'API添加数',
  verified_added_total: '验证通过数',
  cart_selection: '购物车选择',
  payment_type: '付款类型',
  order_sn: '订单号',
  samples_price_return: '样品费退还(元)',
  samples_other_fee: '样品其他费用',
  samples_freight: '样品运费(元)',
  samples_delivery_time: '打样货期(天)',
  factory_img: '工厂图片',
  inquiry_sn: '询价单号',
  porder_sn: '配送单号',
  pay_amount: '付款金额',
  payment_passed: '付款是否成功',
  serial_number: '流水号',
  porder_matched: '配送单匹配',
  purchase_no: '交易号',
  selected_count: '选中商品数',
  purchase_ids: '采购ID列表',
  grid_id: '货位ID',
  grid_number: '货位编号',
  storage_count: '入库数量',
  storage_passed: '入库是否成功',
  customer_count: '客户总数',
  executed_customers: '已执行客户数',
  skipped_customers: '跳过的客户',
  sn_count: '单号数量',
  customers: '客户明细',
  passed: '成功数',
  failed: '失败数',
  total: '总计',
  material_generation_name: '辅料名称',
  material_generation_count: '请求生成数',
  created_count: '已创建数',
  skipped_count: '已跳过数',
  created_list: '已创建列表',
  skipped_list: '已跳过列表',
  completed: '已完成',
  shop_type: '商品来源',
  order_item_count: '每店商品数',
  order_item_num: '每个商品数量',
  logistics_id: '物流方式',
  submit_order: '是否提交订单',
  run_backend_flow: '是否执行后台流程',
  send_num: '每番提出数量',
  warehouse_sku_count: '请求番数',
  actual_warehouse_sku_count: '实际番数',
  total_send_num: '总提出数量',
  selected_sku_ids: '选中SKU',
  selected_warehouse_items: '选中仓库明细',
  order_detail_ids: '仓库明细ID',
  porder_detail_ids: '配送单明细ID',
  porder_logistics_id: '配送物流ID',
  warning: '提示',
  error: '错误信息',
  customer_id: '客户ID',
  duration_ms: '耗时(ms)',
  screenshot: '截图',
  current_url: '当前URL',
  total_box_item_num: '装箱商品总数',
  requested_box_count: '请求箱数',
  kept_box_count: '实际保留箱数',
  box_ids: '箱ID列表',
  box_item_counts: '每箱商品数',
  box_allocations: '箱分配明细',
  direct_box_passed: '直接装箱是否成功',
  deleted_box_ids: '已删除箱ID',
  unfinished_box_ids: '未完成箱ID',
}

const BOOL_TRUE_TEXT = { true: '是', false: '否', True: '是', False: '否' }

function boolText(val) {
  if (typeof val === 'boolean' || val === true || val === false) {
    return BOOL_TRUE_TEXT[String(val)] || String(val)
  }
  return String(val ?? '')
}

export function renderChineseSummary(summary) {
  if (!summary || typeof summary !== 'object' || !Object.keys(summary).length) {
    return '<div class="empty">暂无执行汇总数据</div>'
  }

  const entries = Object.entries(summary).filter(
    ([key]) => key !== 'customers' && !Array.isArray(summary[key]) && typeof summary[key] !== 'object',
  )
  const arrayEntries = Object.entries(summary).filter(
    ([key, val]) => key !== 'customers' && Array.isArray(val) && val.length,
  )
  const objectEntries = Object.entries(summary).filter(
    ([key, val]) => key === 'customers' && Array.isArray(val) && val.length,
  )

  const html = []

  if (entries.length) {
    html.push(
      `<table class="summary-table"><tbody>${entries
        .map(([key, val]) => {
          const label = LABEL_MAP[key] || key
          const display = boolText(val)
          const cellHtml =
            key === 'factory_img' && val
              ? `<img src="${escapeHtml(String(val))}" style="max-width:200px;max-height:200px" />`
              : escapeHtml(display)
          return `<tr><td class="summary-label">${escapeHtml(label)}</td><td class="summary-value">${cellHtml}</td></tr>`
        })
        .join('')}</tbody></table>`,
    )
  }

  if (arrayEntries.length) {
    arrayEntries.forEach(([key, val]) => {
      const label = LABEL_MAP[key] || key
      const display = val
        .map((item) => (typeof item === 'object' && item !== null ? JSON.stringify(item, null, 2) : String(item)))
        .join('\n')
      html.push(
        `<details class="summary-detail"><summary>${escapeHtml(label)}（${val.length}项）</summary><pre class="log-view">${escapeHtml(display)}</pre></details>`,
      )
    })
  }

  if (objectEntries.length) {
    objectEntries.forEach(([key, val]) => {
      html.push(
        `<details class="summary-detail" open><summary>${escapeHtml(LABEL_MAP[key] || key)}（${val.length}条）</summary><table class="summary-table"><tbody>${val
          .map((item) => {
            const itemEntries = Object.entries(item || {})
            return itemEntries
              .map(([k, v]) => {
                const label = LABEL_MAP[k] || k
                const display = boolText(v)
                return `<tr><td class="summary-label">${escapeHtml(label)}</td><td class="summary-value">${escapeHtml(display)}</td></tr>`
              })
              .join('')
          })
          .join('<tr><td colspan="2" style="border-bottom:2px solid var(--border)"></td></tr>')}</tbody></table></details>`,
      )
    })
  }

  const unknownKeys = Object.keys(summary).filter((key) => !LABEL_MAP[key])
  if (unknownKeys.length) {
    html.push(
      `<details class="summary-detail"><summary>其他原始数据</summary><pre class="log-view">${escapeHtml(JSON.stringify(summary, null, 2))}</pre></details>`,
    )
  }

  return html.join('')
}

/**
 * 动态加载 /static/data-factory-agent.js（仅加载一次）
 * 用于调用 window.DataFactoryAgent.renderRecordSummary
 */
let dataFactoryAgentLoaded = null

export function loadDataFactoryAgent() {
  if (dataFactoryAgentLoaded) return dataFactoryAgentLoaded
  if (window.DataFactoryAgent?.renderRecordSummary) {
    dataFactoryAgentLoaded = Promise.resolve(window.DataFactoryAgent)
    return dataFactoryAgentLoaded
  }
  dataFactoryAgentLoaded = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = '/static/data-factory-agent.js'
    script.onload = () => resolve(window.DataFactoryAgent)
    script.onerror = () => reject(new Error('加载 data-factory-agent.js 失败'))
    document.head.appendChild(script)
  })
  return dataFactoryAgentLoaded
}

/**
 * 渲染日志弹窗内容（返回 HTML 字符串）
 * 对齐旧应用 showLog + showLogWithDataAgentSummary
 *
 * 返回结构：{ title, bodyHtml }
 */
export async function buildLogContent(item) {
  const rawText = item.log || ''
  const parsed = parseLog(rawText)

  // 智能体记录：使用 DataFactoryAgent.renderRecordSummary
  if (isDataAgentRecord(parsed)) {
    try {
      const agent = await loadDataFactoryAgent()
      if (agent?.renderRecordSummary) {
        const summaryHtml = agent.renderRecordSummary(parsed, escapeHtml)
        return {
          title: `智能体执行结果 #${item.id}`,
          bodyHtml: `${summaryHtml}<details class="summary-detail"><summary>查看原始日志</summary><pre class="log-view">${escapeHtml(rawText)}</pre></details>`,
        }
      }
    } catch {
      // 加载失败，回退到普通日志
    }
  }

  // 结构化日志：提取 summary 并用 renderChineseSummary 渲染
  const summary = extractSummary(parsed)
  const isStructured = summary && typeof summary === 'object' && Object.keys(summary).length > 0

  if (isStructured) {
    return {
      title: `脚本执行结果 #${item.id}`,
      bodyHtml: `<div class="summary-wrap">${renderChineseSummary(summary)}</div><details class="summary-detail"><summary>查看原始日志</summary><pre class="log-view">${escapeHtml(rawText)}</pre></details>`,
    }
  }

  // 普通日志：直接显示原始文本
  return {
    title: `执行日志 #${item.id}`,
    bodyHtml: `<pre class="log-view">${escapeHtml(rawText)}</pre>`,
  }
}
