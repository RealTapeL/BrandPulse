/**
 * axios 封装（configuredAxios）：
 * - baseURL 指向 /api/v1，自动从 localStorage 注入 Authorization: Bearer <token>
 * - 401 统一处理：清除 token 并跳转 /login；其他错误用 ElMessage 全局提示
 * 开发环境 mock 见 src/mocks/（main.js 中按 VITE_USE_MOCK 挂载）。
 * TODO: 后端 /api/v1 就绪后，确认与 vite proxy / FastAPI 路由前缀一致。
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api/v1',
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
    } else {
      const msg = error.response?.data?.message || `请求失败（${error.message}）`
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default api
