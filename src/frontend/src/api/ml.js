import api from './index'

export async function fetchMLDatasets() {
  const { data } = await api.get('/v1/ml/datasets')
  return data
}

export async function uploadMLDataset(file) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/v1/ml/datasets/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}

export async function startMLTraining(payload = {}) {
  const { data } = await api.post('/v1/ml/forecasting/train', {
    dataset_key: payload.datasetKey || 'store_sales',
    validation_days: payload.validationDays || 28,
    horizon: payload.horizon || 14,
  })
  return data
}

export async function fetchMLRuns({ status = '', page = 1, size = 20 } = {}) {
  const { data } = await api.get('/v1/ml/forecasting/runs', {
    params: { status: status || undefined, page, size },
  })
  return data
}

export async function fetchMLRun(runId) {
  const { data } = await api.get('/v1/ml/forecasting/runs/' + runId)
  return data
}

export async function startMLExport(payload) {
  const { data } = await api.post('/v1/ml/forecasting/exports', {
    model_id: payload.modelId,
    file_format: payload.fileFormat || 'csv',
    run_id: payload.runId || undefined,
  })
  return data
}

export async function fetchMLExports(limit = 50) {
  const { data } = await api.get('/v1/ml/forecasting/exports', { params: { limit } })
  return data
}

export async function fetchMLExport(exportId) {
  const { data } = await api.get('/v1/ml/forecasting/exports/' + exportId)
  return data
}

export async function fetchMLLogs({ operationType = '', page = 1, size = 100 } = {}) {
  const { data } = await api.get('/v1/ml/logs', {
    params: { operation_type: operationType || undefined, page, size },
  })
  return data
}

export async function downloadMLExport(exportId) {
  const response = await api.get('/v1/ml/forecasting/exports/' + exportId + '/download', {
    responseType: 'blob',
    timeout: 120000,
  })
  const contentDisposition = response.headers['content-disposition'] || ''
  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  const filename = filenameMatch?.[1] || `brandpulse_forecast_${exportId}.csv`
  const objectUrl = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function fetchMLForecast(modelId, limit = 100) {
  const { data } = await api.get('/v1/ml/forecasting/models/' + modelId + '/forecast', {
    params: { limit },
  })
  return data
}
