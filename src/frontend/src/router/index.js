import { createRouter, createWebHashHistory } from 'vue-router'
import { ref } from 'vue'

// 路由切换 loading 状态（App.vue 顶部进度条用）
export const routeLoading = ref(false)

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: '数据看板' },
    alias: '/dashboard',
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
  {
    path: '/data-governance',
    name: 'data-governance',
    component: () => import('../views/DataGovernanceView.vue'),
    meta: { title: '数据治理' },
  },
  {
    path: '/ml/forecasting',
    name: 'ml-forecasting',
    component: () => import('../views/MLForecastingView.vue'),
    meta: { title: '机器学习预测' },
  },
  {
    path: '/monitoring',
    name: 'monitoring',
    component: () => import('../views/MonitoringView.vue'),
    meta: { title: '自动监控与告警' },
  },
  {
    path: '/reports',
    name: 'reports',
    component: () => import('../views/ReportsView.vue'),
    meta: { title: '自动报告与导出' },
  },
  {
    path: '/audit',
    name: 'audit',
    component: () => import('../views/AuditView.vue'),
    meta: { title: '操作审计' },
  },
  {
    path: '/brands',
    name: 'brands',
    component: () => import('../views/BrandList.vue'),
    meta: { title: '品牌列表' },
  },
  {
    path: '/brands/:id',
    name: 'brand-detail',
    component: () => import('../views/BrandDetail.vue'),
    meta: { title: '品牌详情' },
  },
  {
    path: '/agent/console',
    name: 'agent-console',
    component: () => import('../views/AgentConsole.vue'),
    meta: { title: 'Agent 控制台' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 鉴权守卫：无 token 一律跳转 /login（public 路由除外），已登录访问 /login 则回首页。
// 直接读 localStorage 而不经过 Pinia，避免守卫与 store 初始化的先后耦合。
router.beforeEach((to, from, next) => {
  routeLoading.value = true
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) {
    return next({ path: '/login', query: { redirect: to.fullPath } })
  }
  if (to.path === '/login' && token) {
    return next({ path: '/' })
  }
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
