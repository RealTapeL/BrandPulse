import { defineStore } from 'pinia'
import { fetchDashboardScopes } from '../api/dashboard'

/**
 * 当前监测范围是全局业务上下文。所有洞察页都从这里读取，避免页面之间
 * 选中了不同的城市/商场/品类却没有提示的情况。
 */
export const useScopeStore = defineStore('scope', {
  state: () => ({
    items: [],
    currentId: '',
    loading: false,
    loaded: false,
    error: '',
  }),
  getters: {
    current(state) {
      return state.items.find((item) => item.scope_id === state.currentId) || null
    },
    label() {
      const scope = this.current
      if (!scope) return '未选择监测范围'
      return [scope.city, scope.mall_name, scope.category].filter(Boolean).join(' · ') || scope.scope_id
    },
  },
  actions: {
    async load({ force = false } = {}) {
      if (this.loaded && !force) return this.items
      this.loading = true
      this.error = ''
      try {
        const result = await fetchDashboardScopes()
        this.items = result.items || []
        if (!this.items.some((item) => item.scope_id === this.currentId)) {
          this.currentId = this.items.find((item) => item.latest_indicator_date)?.scope_id || this.items[0]?.scope_id || ''
        }
        this.loaded = true
        return this.items
      } catch (error) {
        this.error = String(error?.message || error)
        throw error
      } finally {
        this.loading = false
      }
    },
    setCurrent(scopeId) {
      this.currentId = scopeId || ''
    },
  },
})
