import api from './index'

/**
 * GET /api/dashboard
 * 返回 { stat_date, crawl_date, indicators: [...], dp_shops: [...], xhs_notes: [...] }
 */
export function fetchDashboard() {
  return api.get('/v1/dashboard').then((r) => r.data)
}
