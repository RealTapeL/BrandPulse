import api from './index'

export async function fetchMonitoringScopes() {
  const { data } = await api.get('/v1/monitoring/scopes')
  return data
}

export async function fetchCrawlSchedules() {
  const { data } = await api.get('/v1/monitoring/crawl-schedules')
  return data
}

export async function createCrawlSchedule(payload) {
  const { data } = await api.post('/v1/monitoring/crawl-schedules', payload)
  return data
}

export async function updateCrawlSchedule(id, payload) {
  const { data } = await api.put(`/v1/monitoring/crawl-schedules/${id}`, payload)
  return data
}

export async function deleteCrawlSchedule(id) {
  const { data } = await api.delete(`/v1/monitoring/crawl-schedules/${id}`)
  return data
}

export async function runCrawlScheduleNow(id) {
  const { data } = await api.post(`/v1/monitoring/crawl-schedules/${id}/run-now`)
  return data
}
