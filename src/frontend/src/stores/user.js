/**
 * Pinia user store：登录 / 登出，token 与用户信息持久化到 localStorage。
 * axios 实例（src/api/index.js）每次请求自行读取 localStorage 注入 token。
 */
import { defineStore } from 'pinia'
import { login as loginApi } from '../api/auth'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null'),
  }),
  getters: {
    isLoggedIn: (s) => Boolean(s.token),
  },
  actions: {
    async login(username, password) {
      const data = await loginApi(username, password)
      this.token = data.token
      this.user = data.user
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      return data
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    },
  },
})
