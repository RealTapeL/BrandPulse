import api from './index'

/**
 * GET /api/dashboard
 * 返回 { stat_date, crawl_date, indicators: [...], dp_shops: [...], xhs_notes: [...] }
 */
export function fetchDashboard(scopeId = '') {
  return api.get('/v1/dashboard', { params: { scope_id: scopeId || undefined } }).then((r) => r.data)
}

export function fetchDashboardScopes() {
  return api.get('/v1/dashboard/scopes').then((r) => r.data)
}
