/**
 * brands API client 单元测试：mock axios，验证查询参数传递与分页数据结构。
 */
import MockAdapter from 'axios-mock-adapter'
import api from '../../../src/api'
import { getBrands, getBrand, startCrawl } from '../../../src/api/brands'

vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), success: vi.fn() } }))

describe('api/brands', () => {
  let mock

  beforeEach(() => {
    mock = new MockAdapter(api)
  })

  afterEach(() => {
    mock.restore()
  })

  it('getBrands：透传 q/category/city/page/per_page 查询参数', async () => {
    mock.onGet('/brands').reply((config) => {
      expect(config.params).toEqual({ q: '瑞幸', category: '咖啡', city: '苏州', page: 1, per_page: 10 })
      return [200, { items: [], total: 0 }]
    })

    const data = await getBrands({ q: '瑞幸', category: '咖啡', city: '苏州', page: 1, per_page: 10 })
    expect(data).toEqual({ items: [], total: 0 })
  })

  it('getBrand：按 id 请求详情', async () => {
    mock.onGet('/brands/7').reply(200, { brand: { id: 7 }, stats: { indicators: [] }, recent_crawls: [] })

    const data = await getBrand(7)
    expect(data.brand.id).toBe(7)
  })

  it('startCrawl：POST 采集参数并返回 job_id', async () => {
    mock.onPost('/brands/7/crawl').reply((config) => {
      expect(JSON.parse(config.data)).toEqual({ mall: '苏州中心', category: '咖啡', cities: ['苏州'] })
      return [200, { job_id: 'job-1' }]
    })

    const data = await startCrawl(7, { mall: '苏州中心', category: '咖啡', cities: ['苏州'] })
    expect(data.job_id).toBe('job-1')
  })
})
