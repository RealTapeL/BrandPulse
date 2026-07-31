/**
 * axios 封装（configuredAxios）：
 * - baseURL 指向 /api，所有页面从同一 axios 实例请求真实后端
 * - 401 统一处理：清除 token 并跳转 /login；其他错误用 ElMessage 全局提示
 * FastAPI 通过 /api/v1 提供业务接口；Vite 开发服务器将 /api 代理到后端。
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      // hash 路由下直接改 hash，避免引入 router 造成循环依赖
      if (!window.location.hash.startsWith('#/login')) {
        ElMessage.error('登录已过期，请重新登录')
        window.location.hash = '#/login'
      }
    } else if (!error.config?.silent) {
      const msg = error.response?.data?.detail || error.response?.data?.message || `请求失败（${error.message}）`
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default api
