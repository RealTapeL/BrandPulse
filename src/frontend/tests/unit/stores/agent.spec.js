/**
 * agent store 单元测试：执行任务并轮询至终态、失败路径不残留 running 状态。
 */
import MockAdapter from 'axios-mock-adapter'
import { setActivePinia, createPinia } from 'pinia'
import api from '../../../src/api'
import { useAgentStore } from '../../../src/stores/agent'

vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), success: vi.fn() } }))

describe('stores/agent', () => {
  let mock

  beforeEach(() => {
    setActivePinia(createPinia())
    mock = new MockAdapter(api)
  })

  afterEach(() => {
    mock.restore()
  })

  it('execute：拿到 task_id 后轮询到 success，记录历史', async () => {
    mock.onPost('/agent/execute').reply(200, { task_id: 'task-1' })
    mock.onGet('/agent/tasks/task-1').reply(200, {
      id: 'task-1',
      status: 'success',
      input: '统计口碑排名',
      output: '1. % Arabica 4.6',
      logs: [{ time: '10:00:01', message: '任务已接收' }],
    })

    const store = useAgentStore()
    await store.execute('统计口碑排名', { mall: '苏州中心' })

    expect(store.task.status).toBe('success')
    expect(store.task.output).toContain('Arabica')
    expect(store.history).toHaveLength(1)
    expect(store.running).toBe(false)
  })

  it('execute 发起失败：error 落盘且 running 复位', async () => {
    mock.onPost('/agent/execute').reply(500, { message: 'server error' })

    const store = useAgentStore()
    await store.execute('x')

    expect(store.error).toBeTruthy()
    expect(store.running).toBe(false)
    expect(store.task).toBeNull()
  })
})
