import { createRouter, createWebHashHistory } from 'vue-router'
import { ref } from 'vue'
import { useUserStore } from '../stores/user'

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
    path: '/change-password',
    name: 'change-password',
    component: () => import('../views/ChangePassword.vue'),
    meta: { title: '修改密码', passwordChangeOnly: true },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: '工作台', group: '工作台' },
    alias: '/dashboard',
  },
  {
    path: '/assistant',
    name: 'assistant',
    component: () => import('../views/ChatView.vue'),
    meta: { title: '智能助手' },
  },
  { path: '/chat', redirect: '/assistant' },
  {
    path: '/data',
    name: 'data-center',
    component: () => import('../views/DataCenterView.vue'),
    meta: { title: '数据中心', group: '数据中心' },
  },
  { path: '/tables', redirect: { path: '/data', query: { tab: 'tables' } } },
  {
    path: '/formulas',
    name: 'formulas',
    component: () => import('../views/FormulasView.vue'),
    meta: { title: '指标与公式', group: '系统设置' },
  },
  { path: '/data-governance', redirect: { path: '/data', query: { tab: 'quality' } } },
  {
    path: '/ml/forecasting',
    name: 'ml-forecasting',
    component: () => import('../views/MLForecastingView.vue'),
    meta: { title: '实验室 · 机器学习预测', group: '系统设置' },
  },
  {
    path: '/automation',
    name: 'automation-center',
    component: () => import('../views/AutomationCenterView.vue'),
    meta: { title: '自动化中心', group: '自动化中心' },
  },
  { path: '/monitoring', redirect: { path: '/automation', query: { tab: 'collection' } } },
  { path: '/reports', redirect: { path: '/automation', query: { tab: 'reports' } } },
  {
    path: '/audit',
    name: 'audit',
    component: () => import('../views/AuditView.vue'),
    meta: { title: '操作审计', group: '系统设置', permission: 'audit.read' },
  },
  {
    path: '/users',
    name: 'users',
    component: () => import('../views/UserManagementView.vue'),
    meta: { title: '用户与权限', group: '系统设置', permission: 'user.manage' },
  },
  {
    path: '/brands',
    name: 'brands',
    component: () => import('../views/BrandList.vue'),
    meta: { title: '品牌库', group: '品牌洞察', navActive: '/brands' },
  },
  {
    path: '/brands/:id',
    name: 'brand-detail',
    component: () => import('../views/BrandDetail.vue'),
    meta: { title: '品牌详情', group: '品牌洞察', navActive: '/brands' },
  },
  {
    path: '/opportunities',
    name: 'opportunities',
    component: () => import('../views/OpportunityRadarView.vue'),
    meta: { title: '机会雷达', group: '品牌洞察', navActive: '/opportunities' },
  },
  {
    path: '/watchlist',
    name: 'watchlist',
    component: () => import('../views/WatchlistView.vue'),
    meta: { title: '关注清单', group: '品牌洞察', navActive: '/watchlist' },
  },
  {
    path: '/assistant/advanced',
    name: 'agent-console',
    component: () => import('../views/AgentConsole.vue'),
    meta: { title: '智能助手 · 高级任务', group: '系统设置', permission: 'agent.operate' },
  },
  { path: '/agent/console', redirect: '/assistant/advanced' },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 鉴权守卫从 HttpOnly 刷新 Cookie 恢复会话；后端仍是最终权限裁决方。
router.beforeEach(async (to) => {
  routeLoading.value = true
  const userStore = useUserStore()
  if (to.meta.public) {
    await userStore.restoreSession()
    return userStore.isLoggedIn ? { path: '/' } : true
  }
  const restored = await userStore.restoreSession()
  if (!restored) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (userStore.user?.must_change_password && !to.meta.passwordChangeOnly) {
    return { path: '/change-password' }
  }
  if (to.meta.passwordChangeOnly && !userStore.user?.must_change_password) {
    return { path: '/' }
  }
  if (to.meta.permission && !userStore.hasPermission(to.meta.permission)) {
    return { path: '/' }
  }
  return true
})

router.afterEach((to) => {
  routeLoading.value = false
  document.title = to.meta.title
    ? `${to.meta.title} · BrandPulse 招商品牌情报平台`
    : 'BrandPulse 招商品牌情报平台'
  window.scrollTo({ top: 0 })
})

export default router
