/**
 * 认证接口：POST /api/v1/auth/login
 * body: { username, password }
 * resp: { token, user: { id, username, role } }
 */
import api from './index'

export function login(username, password) {
  return api.post('/v1/auth/login', { username, password }).then((r) => r.data)
}
