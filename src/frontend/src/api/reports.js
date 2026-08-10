import api from './index'

export async function fetchReportReadiness(scopeId) {
  const { data } = await api.get(`/v1/reports/readiness/${scopeId}`)
  return data
}

export async function createReport(payload) {
  const { data } = await api.post('/v1/reports', payload)
  return data
}

export async function fetchReports(scopeId = '') {
  const { data } = await api.get('/v1/reports', { params: { scope_id: scopeId || undefined } })
  return data
}

export async function downloadReport(reportId) {
  const response = await api.get(`/v1/reports/${reportId}/download`, { responseType: 'blob', timeout: 120000 })
  const header = response.headers['content-disposition'] || ''
  const match = header.match(/filename="?([^";]+)"?/i)
  const objectUrl = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = match?.[1] || `brandpulse_report_${reportId}.xlsx`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function fetchReportSchedules() {
  const { data } = await api.get('/v1/reports/schedules/list')
  return data
}

export async function createReportSchedule(payload) {
  const { data } = await api.post('/v1/reports/schedules', payload)
  return data
}

export async function updateReportSchedule(id, payload) {
  const { data } = await api.put(`/v1/reports/schedules/${id}`, payload)
  return data
}

export async function deleteReportSchedule(id) {
  const { data } = await api.delete(`/v1/reports/schedules/${id}`)
  return data
}
