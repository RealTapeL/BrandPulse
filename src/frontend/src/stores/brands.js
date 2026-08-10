/**
 * Pinia brands store：品牌列表（分页/搜索）、品牌详情、发起采集。
 * 错误信息统一由 axios 拦截器弹窗，store 里记录 error 供页面展示 retry 区域。
 */
import { defineStore } from 'pinia'
import { getBrands, getBrand, getBrandFilters, startCrawl, getCrawlJob } from '../api/brands'

export const useBrandsStore = defineStore('brands', {
  state: () => ({
    items: [],
    total: 0,
    page: 1,
    perPage: 10,
    query: { q: '', category: '', city: '' },
    filters: { categories: [], cities: [] },
    loading: false,
    error: null,
    detail: null,
    detailLoading: false,
    detailError: null,
    detailRequestId: 0,
  }),
  actions: {
    async fetchList({ page = this.page } = {}) {
      this.loading = true
      this.error = null
      this.page = page
      try {
        const data = await getBrands({
          q: this.query.q || undefined,
          category: this.query.category || undefined,
          city: this.query.city || undefined,
          page: this.page,
          per_page: this.perPage,
        })
        this.items = data.items
        this.total = data.total
      } catch (e) {
        this.error = e
        this.items = []
        this.total = 0
      } finally {
        this.loading = false
      }
    },
    async fetchFilters() {
      this.filters = await getBrandFilters()
    },
    async fetchDetail(id) {
      const requestId = ++this.detailRequestId
      this.detailLoading = true
      this.detailError = null
      this.detail = null
      try {
        const result = await getBrand(id)
        if (requestId === this.detailRequestId) this.detail = result
      } catch (e) {
        if (requestId === this.detailRequestId) this.detailError = e
      } finally {
        if (requestId === this.detailRequestId) this.detailLoading = false
      }
    },
    // 发起采集，返回 { job_id }
    async crawl(id, payload) {
      return startCrawl(id, payload)
    },
    async fetchCrawlJob(id) {
      return getCrawlJob(id)
    },
  },
})
