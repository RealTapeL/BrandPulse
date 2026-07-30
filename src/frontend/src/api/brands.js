/**
 * 品牌接口（/api/v1/brands）：
 * getBrands  列表（q/category/city/page/per_page 查询参数）
 * getBrand   详情（含 stats.indicators 与 recent_crawls）
 * startCrawl 发起采集任务 → { job_id }
 * TODO: 后端按契约实现后，mock 见 src/mocks/index.js。
 */
import api from './index'

export function getBrands(params = {}) {
  return api.get('/brands', { params }).then((r) => r.data)
}

export function getBrand(id) {
  return api.get(`/brands/${id}`).then((r) => r.data)
}

export function startCrawl(id, payload) {
  return api.post(`/brands/${id}/crawl`, payload).then((r) => r.data)
}
