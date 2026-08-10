import api from './index'

export async function fetchAlerts() {
  const { data } = await api.get('/v1/alerts')
  return data
}

export async function createAlert(payload) {
  const { data } = await api.post('/v1/alerts', payload)
  return data
}

export async function updateAlert(id, payload) {
  const { data } = await api.put(`/v1/alerts/${id}`, payload)
  return data
}

export async function deleteAlert(id) {
  const { data } = await api.delete(`/v1/alerts/${id}`)
  return data
}

export async function checkAlertsNow() {
  const { data } = await api.post('/v1/alerts/check-now')
  return data
}

export async function fetchAlertHistory(limit = 100) {
  const { data } = await api.get('/v1/alerts/history', { params: { limit } })
  return data
}
