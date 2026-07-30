import { request } from './http'
import { fetchDashboard } from './dashboard'

/**
 * 数据表查看 API。
 *
 * 后端契约（待实现）：
 *   GET /api/tables/{table_name}?page=1&size=20&keyword=
 *   返回 { total: number, rows: [...] }
 *
 * 当前实现：后端未提供该接口，先用 GET /api/dashboard 返回的
 * dp_shops / xhs_notes / indicators 三个数组在前端做筛选分页。
 * 后端接口上线后，把下面的 USE_BACKEND_TABLE_API 置为 true 即可（一行切换）。
 */
const USE_BACKEND_TABLE_API = false

export const TABLES = [
  {
    name: 'dp_shop_metrics',
    label: '点评门店',
    source: 'dp_shops',
    desc: '大众点评门店采集指标（最新采集日）',
    columns: [
      { prop: 'shop_name', label: '门店名称', sortable: true, minWidth: 220 },
      { prop: 'score', label: '评分', sortable: true, width: 100 },
      { prop: 'review_count', label: '评价数', sortable: true, width: 110 },
      { prop: 'avg_price', label: '人均(元)', sortable: true, width: 110 },
      { prop: 'business_area', label: '商圈', sortable: true, minWidth: 130 },
      { prop: 'place', label: '位置', sortable: false, minWidth: 150 },
    ],
  },
  {
    name: 'xhs_notes',
    label: '小红书笔记',
    source: 'xhs_notes',
    desc: '小红书品牌相关笔记（按点赞降序，Top 100）',
    columns: [
      { prop: 'title', label: '标题', sortable: false, minWidth: 300 },
      { prop: 'author_name', label: '作者', sortable: true, width: 140 },
      { prop: 'likes', label: '点赞数', sortable: true, width: 100 },
      { prop: 'publish_time', label: '发布时间', sortable: true, width: 140 },
    ],
  },
  {
    name: 'brand_indicators_daily',
    label: '指标日表',
    source: 'indicators',
    desc: '门店级日度指标（口碑分 / 热度指数 / SOV，最新统计日）',
    columns: [
      { prop: 'entity_name', label: '门店名称', sortable: true, minWidth: 220 },
      { prop: 'weighted_score', label: '口碑分', sortable: true, width: 110 },
      { prop: 'heat_index', label: '热度指数', sortable: true, width: 110 },
      { prop: 'sov', label: 'SOV 声量份额', sortable: true, width: 140 },
    ],
  },
]

export function getTableConfig(name) {
  return TABLES.find((t) => t.name === name) || TABLES[0]
}

function matchKeyword(row, keyword) {
  const kw = keyword.trim().toLowerCase()
  if (!kw) return true
  return Object.values(row).some((v) => v != null && String(v).toLowerCase().includes(kw))
}

/**
 * 查询数据表（统一签名，前后端两种实现返回一致结构）。
 * @returns {Promise<{ total: number, rows: object[] }>}
 */
export async function fetchTableData(tableName, { page = 1, size = 20, keyword = '', sortProp = '', sortOrder = '' } = {}) {
  if (USE_BACKEND_TABLE_API) {
    const params = new URLSearchParams({ page, size, keyword })
    if (sortProp) params.set('sort_prop', sortProp)
    if (sortOrder) params.set('sort_order', sortOrder)
    return request(`/api/tables/${tableName}?${params}`)
  }

  // ---- 本地实现：复用 /api/dashboard 数据，前端筛选 / 排序 / 分页 ----
  const conf = getTableConfig(tableName)
  const data = await fetchDashboard()
  let rows = (data[conf.source] || []).slice()

  if (keyword.trim()) rows = rows.filter((r) => matchKeyword(r, keyword))

  if (sortProp && sortOrder) {
    const dir = sortOrder === 'ascending' ? 1 : -1
    rows.sort((a, b) => {
      const va = a[sortProp]
      const vb = b[sortProp]
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
      return String(va).localeCompare(String(vb), 'zh-CN') * dir
    })
  }

  const total = rows.length
  const start = (page - 1) * size
  return { total, rows: rows.slice(start, start + size) }
}
