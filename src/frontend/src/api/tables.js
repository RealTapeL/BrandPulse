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
    name: 'raw_observations',
    label: '原始观测',
    desc: '当前可信范围内已采集、可追溯的原始来源记录',
    requiresScope: true,
    columns: [
      { prop: 'source_name', label: '来源', sortable: true, minWidth: 170 },
      { prop: 'record_type', label: '记录类型', sortable: true, minWidth: 140 },
      { prop: 'observed_date', label: '观测日期', sortable: true, width: 120 },
      { prop: 'source_record_key', label: '来源记录键', sortable: true, minWidth: 220 },
      { prop: 'entity_mapping_status', label: '实体映射', sortable: true, width: 120 },
      { prop: 'category_mapping_status', label: '品类映射', sortable: true, width: 120 },
      { prop: 'quality_status', label: '质量状态', sortable: true, width: 120 },
      { prop: 'source_url', label: '来源链接', sortable: true, minWidth: 220 },
    ],
  },
  {
    name: 'metric_observations',
    label: '快照指标',
    desc: '当前可信范围下、绑定快照与口径版本的指标事实',
    requiresScope: true,
    columns: [
      { prop: 'snapshot_id', label: '快照 ID', sortable: true, minWidth: 210 },
      { prop: 'metric_key', label: '指标', sortable: true, minWidth: 190 },
      { prop: 'entity_type', label: '实体层级', sortable: true, width: 110 },
      { prop: 'entity_key', label: '实体键', sortable: true, minWidth: 180 },
      { prop: 'value', label: '值', sortable: true, width: 130 },
      { prop: 'unit', label: '单位', sortable: true, width: 90 },
      { prop: 'quality_status', label: '质量状态', sortable: true, width: 120 },
      { prop: 'metric_version', label: '口径版本', sortable: true, minWidth: 130 },
      { prop: 'calculated_at', label: '计算时间', sortable: true, minWidth: 180 },
    ],
  },
  {
    name: 'store_operations',
    label: '门店经营数据',
    desc: 'Excel 导入的真实销售、成本与合同经营记录',
    columns: [
      { prop: 'record_date', label: '日期', sortable: true, width: 120 },
      { prop: 'brand_id', label: '品牌 ID', sortable: true, width: 120 },
      { prop: 'store_id', label: '门店 ID', sortable: true, width: 170 },
      { prop: 'sales_amount', label: '销售额', sortable: true, width: 120 },
      { prop: 'order_count', label: '订单数', sortable: true, width: 100 },
      { prop: 'customer_price', label: '客单价', sortable: true, width: 100 },
      { prop: 'customer_flow', label: '客流量', sortable: true, width: 100 },
      { prop: 'rent', label: '租金', sortable: true, width: 100 },
      { prop: 'rent_to_sales_ratio', label: '租售比(%)', sortable: true, width: 120 },
      { prop: 'sales_per_sqm', label: '坪效', sortable: true, width: 100 },
      { prop: 'contract_end', label: '合同到期', sortable: true, width: 120 },
      { prop: 'data_source', label: '数据来源', sortable: false, minWidth: 180 },
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
export async function fetchTableData(tableName, { page = 1, size = 20, keyword = '', sortProp = '', sortOrder = '', scopeId = '' } = {}) {
  const { data } = await api.get(`/v1/tables/${tableName}`, {
    params: { page, size, keyword: keyword.trim(), sort_prop: sortProp, sort_order: sortOrder, scope_id: scopeId },
  })
  return data
}
