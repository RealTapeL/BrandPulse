import api from './index'

export async function fetchCases(params = {}) {
  const { data } = await api.get('/v1/cases', { params })
  return data
}

export async function fetchCase(caseId) {
  const { data } = await api.get(`/v1/cases/${caseId}`)
  return data
}

export async function createCase(payload) {
  const { data } = await api.post('/v1/cases', payload)
  return data
}

export async function createCaseFromSource(payload) {
  const { data } = await api.post('/v1/cases/from-source', payload)
  return data
}

export async function updateCase(caseId, payload) {
  const { data } = await api.put(`/v1/cases/${caseId}`, payload)
  return data
}

export async function fetchCaseMetrics() {
  const { data } = await api.get('/v1/cases/metrics')
  return data
}
