/**
 * user store 单元测试：mock axios 后端，验证登录成功写入 token/user、失败不残留状态。
 */
import MockAdapter from 'axios-mock-adapter'
import { setActivePinia, createPinia } from 'pinia'
import api from '../../../src/api'
import { useUserStore } from '../../../src/stores/user'

// jsdom 环境下屏蔽 ElMessage 真实弹窗
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), success: vi.fn() } }))

describe('stores/user', () => {
  let mock

  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    mock = new MockAdapter(api)
  })

  afterEach(() => {
    mock.restore()
  })

  it('登录成功：保存 token 与 user 到 state 和 localStorage', async () => {
    mock.onPost('/auth/login').reply(200, {
      token: 'mock-jwt-token-for-demo',
      user: { id: 1, username: 'admin', role: 'admin' },
    })

    const store = useUserStore()
    await store.login('admin', '123456')

    expect(store.isLoggedIn).toBe(true)
    expect(store.token).toBe('mock-jwt-token-for-demo')
    expect(store.user.username).toBe('admin')
    expect(localStorage.getItem('token')).toBe('mock-jwt-token-for-demo')
    // axios 请求头注入 token
    expect(mock.history.post[0].headers.Authorization).toBeUndefined() // 登录前无 token
  })

  it('登录成功后请求自动携带 Authorization', async () => {
    mock.onPost('/auth/login').reply(200, {
      token: 't-123',
      user: { id: 1, username: 'admin', role: 'admin' },
    })
    mock.onGet('/brands').reply(200, { items: [], total: 0 })

    const store = useUserStore()
    await store.login('admin', '123456')
    await api.get('/brands')

    expect(mock.history.get[0].headers.Authorization).toBe('Bearer t-123')
  })

  it('登录失败：抛出错误且不写入 token', async () => {
    mock.onPost('/auth/login').reply(400, { message: '用户名和密码不能为空' })

    const store = useUserStore()
    await expect(store.login('', '')).rejects.toThrow()
    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('logout：清空 state 与 localStorage', async () => {
    mock.onPost('/auth/login').reply(200, {
      token: 't-123',
      user: { id: 1, username: 'admin', role: 'admin' },
    })

    const store = useUserStore()
    await store.login('admin', '123456')
    store.logout()

    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })
})
