import api from './index'

export async function fetchSnapshots({ scopeId = '', status = '', limit = 100 } = {}) {
  const { data } = await api.get('/v1/snapshots', {
    params: { scope_id: scopeId || undefined, status: status || undefined, limit },
  })
  return data.items || []
}

export async function fetchSourceHealth(scopeId) {
  const { data } = await api.get(`/v1/snapshots/source-health/${scopeId}`)
  return data.items || []
}

export async function fetchSnapshot(snapshotId) {
  const { data } = await api.get(`/v1/snapshots/${snapshotId}`)
  return data
}

export async function publishSnapshot(snapshotId) {
  const { data } = await api.post(`/v1/snapshots/${snapshotId}/publish`)
  return data
}
