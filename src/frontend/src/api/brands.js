/**
 * 品牌接口（/api/v1/brands）：
 * getBrands  列表（q/category/city/page/per_page 查询参数）
 * getBrand   详情（含 stats.indicators 与 recent_crawls）
 * startCrawl 发起采集任务 → { job_id }
 */
import api from './index'

export function getBrands(params = {}) {
  return api.get('/v1/brands', { params }).then((r) => r.data)
}

export function getBrand(id) {
  return api.get(`/v1/brands/${id}`).then((r) => r.data)
}

export function startCrawl(id, payload) {
  return api.post(`/v1/brands/${id}/crawl`, payload).then((r) => r.data)
}

export function getCrawlJob(id) {
  return api.get(`/v1/crawl_jobs/${id}`).then((r) => r.data)
}

export function getBrandFilters() {
  return api.get('/v1/brands/filters').then((r) => r.data)
}

export function getBrandIndicatorSeries(id, indicator) {
  return api.get(`/v1/brands/${id}/indicator-series`, { params: { indicator } }).then((r) => r.data)
}
