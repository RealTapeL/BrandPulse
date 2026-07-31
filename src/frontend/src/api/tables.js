import api from './index'

/**
 * 数据表查看 API。
 *
 * 后端契约：
 *   GET /api/v1/tables/{table_name}?page=1&size=20&keyword=
 *   返回 { total: number, rows: [...] }
 *
 * 由后端白名单表配置执行筛选、排序和分页，避免在浏览器下载全量数据。
 */
export const TABLES = [
  {
    name: 'dp_shop_metrics',
    label: '点评门店',
    desc: '大众点评门店采集指标',
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
    desc: '小红书品牌相关笔记',
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
    desc: '门店级日度指标（口碑分 / 热度指数 / SOV）',
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

/**
 * 查询数据表。
 * @returns {Promise<{ total: number, rows: object[] }>}
 */
export async function fetchTableData(tableName, { page = 1, size = 20, keyword = '', sortProp = '', sortOrder = '' } = {}) {
  const { data } = await api.get(`/v1/tables/${tableName}`, {
    params: { page, size, keyword: keyword.trim(), sort_prop: sortProp, sort_order: sortOrder },
  })
  return data
}
