import api from './index'

export async function fetchAuditEvents(params = {}) {
  const { data } = await api.get('/v1/audit/events', { params })
  return data
}

export async function fetchConfigurationStatus() {
  const { data } = await api.get('/v1/system/configuration')
  return data
}
