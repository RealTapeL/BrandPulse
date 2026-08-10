import api from './index'

function asFormData(file) {
  const form = new FormData()
  form.append('file', file)
  return form
}

export async function previewOperations(file) {
  const { data } = await api.post('/v1/operations/preview', asFormData(file), {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function importOperations(file) {
  const { data } = await api.post('/v1/operations/import', asFormData(file), {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
