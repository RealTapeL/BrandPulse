import { request } from './http'

/**
 * GET /api/dashboard
 * 返回 { stat_date, crawl_date, indicators: [...], dp_shops: [...], xhs_notes: [...] }
 */
export function fetchDashboard() {
  return request('/api/dashboard')
}
