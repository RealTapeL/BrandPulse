import api from './index'

export async function fetchGovernanceSummary() {
  const { data } = await api.get('/v1/data-governance/summary')
  return data
}

export async function runGovernanceScan() {
  const { data } = await api.post('/v1/data-governance/scan')
  return data
}

export async function fetchQualityIssues({ status = '', severity = '', page = 1, size = 100 } = {}) {
  const { data } = await api.get('/v1/data-governance/issues', {
    params: { status: status || undefined, severity: severity || undefined, page, size },
  })
  return data
}

export async function updateQualityIssue(issueId, payload) {
  const { data } = await api.put(`/v1/data-governance/issues/${issueId}`, payload)
  return data
}

export async function fetchBrandAliases({ brandId = '', status = '' } = {}) {
  const { data } = await api.get('/v1/data-governance/brand-aliases', {
    params: { brand_id: brandId || undefined, status: status || undefined },
  })
  return data.items || []
}

export async function fetchStoreAliases({ status = 'pending', page = 1, size = 100 } = {}) {
  const { data } = await api.get('/v1/data-governance/store-aliases', {
    params: { status: status || undefined, page, size },
  })
  return data
}

export async function fetchStoreOptions({ q = '', city = '' } = {}) {
  const { data } = await api.get('/v1/data-governance/store-options', {
    params: { q: q || undefined, city: city || undefined, size: 300 },
  })
  return data.items || []
}

export async function updateStoreAlias(aliasId, payload) {
  const { data } = await api.put(`/v1/data-governance/store-aliases/${aliasId}`, payload)
  return data
}

export async function fetchLineage({ sourceName = '', size = 100 } = {}) {
  const { data } = await api.get('/v1/data-governance/lineage', {
    params: { source_name: sourceName || undefined, size },
  })
  return data.items || []
}

export async function fetchRawLineage({ sourceName = '', crawlJobId = '', runId = '', size = 100 } = {}) {
  const { data } = await api.get('/v1/data-governance/lineage/records', {
    params: {
      source_name: sourceName || undefined,
      crawl_job_id: crawlJobId || undefined,
      run_id: runId || undefined,
      size,
    },
  })
  return data.items || []
}
