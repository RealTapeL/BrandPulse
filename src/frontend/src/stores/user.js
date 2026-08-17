/**
 * Pinia 用户会话：Access Token 只在内存中保存；刷新页面通过 HttpOnly Cookie 恢复。
 */
import { defineStore } from 'pinia'
import { changePassword as changePasswordApi, login as loginApi, logout as logoutApi, refreshSession } from '../api/auth'
import { clearAccessToken, setAccessToken } from '../auth/session'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: '',
    user: null,
    initialized: false,
  }),
  getters: {
    isLoggedIn: (s) => Boolean(s.token),
    hasPermission: (s) => (permission) => Boolean(s.user?.permissions?.includes(permission)),
  },
  actions: {
    applySession(data) {
      this.token = data.token
      this.user = data.user
      setAccessToken(data.token)
    },
    async login(username, password) {
      const data = await loginApi(username, password)
      this.applySession(data)
      this.initialized = true
      return data
    },
    async restoreSession() {
      if (this.initialized) return this.isLoggedIn
      try {
        const data = await refreshSession()
        this.applySession(data)
        return true
      } catch {
        this.clearSession()
        return false
      } finally {
        this.initialized = true
      }
    },
    clearSession() {
      this.token = ''
      this.user = null
      clearAccessToken()
    },
    async logout() {
      const accessToken = this.token
      // 先本地失效，避免网络异常期间页面仍能继续发起带凭据请求。
      this.clearSession()
      this.initialized = true
      try {
        if (accessToken) await logoutApi(accessToken)
      } catch {
        // 会话即使无法通知服务端也已不再被当前浏览器使用；刷新令牌仍会自然过期。
      }
    },
    async changePassword(currentPassword, newPassword) {
      await changePasswordApi(currentPassword, newPassword)
      this.clearSession()
      this.initialized = true
    },
  },
})
