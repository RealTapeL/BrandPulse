/**
 * 开发环境 mock：用 axios-mock-adapter 拦截 /api/v1/*，返回 mocks/*.json 数据。
 * 仅在 main.js 检测到 VITE_USE_MOCK !== 'false' 的开发模式下挂载。
 * TODO: 后端就绪后改为默认关闭（.env.development 设 VITE_USE_MOCK=false），并逐步删除。
 */
import MockAdapter from 'axios-mock-adapter'
import auth from './auth.json'
import brandsData from './brands.json'
import brandDetail from './brand-detail.json'
import indicatorsData from './indicators.json'

// Agent 任务的轮询计数与输入（模块级，跨请求保持）
const taskPollCount = {}
const taskInputs = {}

// GET /brands 的查询过滤 + 分页（q 模糊匹配名称，category/city 精确匹配）
function queryBrands(params = {}) {
  const { q, category, city, page = 1, per_page = 10 } = params
  let items = brandsData.items
  if (q) items = items.filter((b) => b.name.toLowerCase().includes(String(q).toLowerCase()))
  if (category) items = items.filter((b) => b.category === category)
  if (city) items = items.filter((b) => b.city === city)
  const p = Number(page)
  const pp = Number(per_page)
  return { items: items.slice((p - 1) * pp, p * pp), total: items.length }
}

export function setupMock(api) {
  const mock = new MockAdapter(api, { delayResponse: 300 })

  // POST /api/v1/auth/login：演示环境任意非空账号密码均可登录
  mock.onPost('/auth/login').reply((config) => {
    const { username, password } = JSON.parse(config.data || '{}')
    if (!username || !password) {
      return [400, { message: '用户名和密码不能为空' }]
    }
    return [200, { ...auth, user: { ...auth.user, username } }]
  })

  // GET /api/v1/brands
  mock.onGet('/brands').reply((config) => [200, queryBrands(config.params)])

  // GET /api/v1/brands/{id}：按 id 换品牌主体，统计与采集记录复用演示数据
  mock.onGet(/\/brands\/\d+$/).reply((config) => {
    const id = Number(config.url.match(/\/brands\/(\d+)$/)[1])
    const brand = brandsData.items.find((b) => b.id === id)
    if (!brand) return [404, { message: '品牌不存在' }]
    return [200, { ...brandDetail, brand }]
  })

  // POST /api/v1/brands/{id}/crawl
  mock.onPost(/\/brands\/\d+\/crawl$/).reply(() => [
    200,
    { job_id: `job-${Date.now()}` },
  ])

  // GET /api/v1/indicators
  mock.onGet('/indicators').reply(() => [200, indicatorsData])

  // POST /api/v1/agent/execute → { task_id }
  mock.onPost('/agent/execute').reply((config) => {
    const { prompt } = JSON.parse(config.data || '{}')
    if (!prompt) return [400, { message: 'prompt 不能为空' }]
    const taskId = `task-${Date.now()}`
    taskPollCount[taskId] = 0
    taskInputs[taskId] = prompt
    return [200, { task_id: taskId }]
  })

  // GET /api/v1/agent/tasks/{id}：前 2 次轮询返回 running，之后返回 success（模拟任务推进）
  mock.onGet(/\/agent\/tasks\/[\w-]+$/).reply((config) => {
    const id = config.url.match(/\/agent\/tasks\/([\w-]+)$/)[1]
    const count = (taskPollCount[id] = (taskPollCount[id] ?? 0) + 1)
    const input = taskInputs[id] || ''
    const base = {
      id,
      input,
      logs: [
        { time: '10:00:01', message: '任务已接收，排队执行' },
        { time: '10:00:03', message: '调用工具 query_db 查询品牌指标' },
      ],
    }
    if (count <= 2) {
      return [200, { ...base, status: 'running', output: null }]
    }
    return [
      200,
      {
        ...base,
        status: 'success',
        logs: [...base.logs, { time: '10:00:08', message: '分析完成，生成结论' }],
        output:
          '苏州中心咖啡品牌口碑分排名（演示数据）：\n1. % Arabica 4.6\n2. Peet\'s 皮爷咖啡 4.5\n3. M Stand 4.4\n\n建议关注 Manner Coffee 的近期热度上升趋势。',
      },
    ]
  })

  // 未覆盖的接口统一 404，便于发现哪些契约还没补 mock
  mock.onAny().reply(404, { message: 'mock 未覆盖该接口' })
  return mock
}
