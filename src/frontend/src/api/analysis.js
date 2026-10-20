import api from './index'

/**
 * 统一分析查询层。
 * 返回 scope/snapshot/filters/metrics/series/ranking/evidence/quality/warnings。
 */
export function fetchAnalysis(params = {}) {
  return api.get('/v1/analysis', { params }).then((response) => response.data)
}

export function fetchAnalysisMetrics() {
  return api.get('/v1/analysis/metrics').then((response) => response.data)
}
