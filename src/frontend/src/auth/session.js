/**
 * 短期 Access Token 只保存在运行内存，不写入 localStorage / sessionStorage。
 * 浏览器刷新后由 HttpOnly 刷新 Cookie 向服务端换取新 Token。
 */
let accessToken = ''

export function getAccessToken() {
  return accessToken
}

export function setAccessToken(token) {
  accessToken = token || ''
}

export function clearAccessToken() {
  accessToken = ''
}
