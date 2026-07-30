/**
 * 统一 HTTP 请求封装：超时控制、错误统一提示（ElMessage）。
 * 生产环境由 FastAPI 静态托管 dist，前端与 API 同源，直接使用相对路径。
 */
import { ElMessage } from 'element-plus'

export async function request(url, { method = 'GET', body, timeout = 15000, silent = false } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const resp = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    if (!resp.ok) {
      const err = new Error(`HTTP ${resp.status}`)
      err.status = resp.status
      throw err
    }
    return await resp.json()
  } catch (e) {
    if (!silent) {
      const msg = e.name === 'AbortError' ? '请求超时，请稍后重试' : `请求失败（${e.message}）`
      ElMessage.error(msg)
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}
