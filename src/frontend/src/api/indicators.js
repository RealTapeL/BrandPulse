/**
 * 指标接口（/api/v1/indicators）：
 * getIndicators({ brand_id, start, end, indicator }) → { series: [{date,value}], meta }
 */
import api from './index'

export function getIndicators(params = {}) {
  return api.get('/indicators', { params }).then((r) => r.data)
}
