import { createRouter, createWebHashHistory } from 'vue-router'
import { ref } from 'vue'

// 路由切换 loading 状态（App.vue 顶部进度条用）
export const routeLoading = ref(false)

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: '数据看板' },
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('../views/ChatView.vue'),
    meta: { title: '对话助手' },
  },
  {
    path: '/tables',
    name: 'tables',
    component: () => import('../views/TablesView.vue'),
    meta: { title: '数据表查看' },
  },
  {
    path: '/formulas',
    name: 'formulas',
    component: () => import('../views/FormulasView.vue'),
    meta: { title: '指标公式管理' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  routeLoading.value = true
  next()
})

router.afterEach((to) => {
  routeLoading.value = false
  document.title = to.meta.title
    ? `${to.meta.title} · BrandPulse 招商品牌情报平台`
    : 'BrandPulse 招商品牌情报平台'
  window.scrollTo({ top: 0 })
})

export default router
