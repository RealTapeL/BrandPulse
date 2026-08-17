/** 管理员账号、角色和临时密码管理。 */
import api from './index'

export function fetchUsers() {
  return api.get('/v1/users').then((r) => r.data)
}

export function createUser(payload) {
  return api.post('/v1/users', payload).then((r) => r.data)
}

export function updateUser(userId, payload) {
  return api.put(`/v1/users/${userId}`, payload).then((r) => r.data)
}

export function resetUserPassword(userId, temporaryPassword = undefined) {
  const payload = temporaryPassword ? { temporary_password: temporaryPassword } : {}
  return api.post(`/v1/users/${userId}/reset-password`, payload).then((r) => r.data)
}
