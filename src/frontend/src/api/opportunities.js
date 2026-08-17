import api from './index'

export async function fetchOpportunities({ scopeId, snapshotId = '', signalClass = '', lifecycleStatus = '', limit = 100 } = {}) {
  const { data } = await api.get('/v1/opportunities', {
    params: {
      scope_id: scopeId,
      snapshot_id: snapshotId || undefined,
      signal_class: signalClass || undefined,
      lifecycle_status: lifecycleStatus || undefined,
      limit,
    },
  })
  return data
}

export async function updateOpportunity(signalId, payload) {
  const { data } = await api.put(`/v1/opportunities/${signalId}`, payload)
  return data
}
