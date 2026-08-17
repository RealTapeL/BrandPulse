/**
 * 认证接口：POST /api/v1/auth/login
 * body: { username, password }
 * resp: { token, user: { id, username, role, permissions } }
 */
import api from './index'

export function login(username, password) {
  return api.post('/v1/auth/login', { username, password }).then((r) => r.data)
}

export function refreshSession() {
  return api.post('/v1/auth/refresh', {}, { silent: true, skipAuthRedirect: true }).then((r) => r.data)
}

export function logout(accessToken = '') {
  return api.post('/v1/auth/logout', {}, {
    silent: true,
    skipAuthRedirect: true,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  })
}

export function changePassword(currentPassword, newPassword) {
  return api.post('/v1/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  }).then((r) => r.data)
}
