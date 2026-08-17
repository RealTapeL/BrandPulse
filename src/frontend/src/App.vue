<template>
  <!-- 登录页：全屏裸布局，不带侧边栏 -->
  <router-view v-if="isBarePage" />
  <el-container v-else class="layout">
    <el-aside :width="sidebarWidth" class="sidebar" :class="{ collapsed: sidebarCollapsed, 'sidebar-mobile-open': mobileSidebarOpen }">
      <div class="brand">
        <el-icon :size="22"><DataAnalysis /></el-icon>
        <div class="brand-text">
          <span class="brand-name">BrandPulse</span>
          <span class="brand-sub">招商品牌情报平台</span>
        </div>
      </div>
      <el-menu
        class="sidebar-menu"
        :default-active="activeMenu"
        :collapse="sidebarCollapsed"
        :collapse-transition="false"
        router
        @select="closeMobileSidebar"
      >
        <template v-for="group in visibleGroups" :key="group.title">
          <el-menu-item v-if="group.path" :index="group.path">
            <el-icon><component :is="group.icon" /></el-icon><template #title>{{ group.title }}</template>
          </el-menu-item>
          <el-sub-menu v-else :index="group.id">
            <template #title><el-icon><component :is="group.icon" /></el-icon><span>{{ group.title }}</span></template>
            <el-menu-item v-for="item in group.items" :key="item.path" :index="item.path"><el-icon><component :is="item.icon" /></el-icon><template #title>{{ item.title }}</template></el-menu-item>
          </el-sub-menu>
        </template>
      </el-menu>
      <div class="sidebar-footer"><el-icon><InfoFilled /></el-icon><span>当前范围由顶部选择器统一控制</span></div>
    </el-aside>

    <el-container class="main-wrap">
      <!-- 顶部栏 -->
      <el-header class="topbar" height="56px">
        <div class="topbar-left">
          <button type="button" class="menu-toggle" aria-label="切换导航菜单" @click="toggleSidebar">
            <el-icon :size="19"><Fold v-if="!sidebarCollapsed && !isNarrow" /><Expand v-else /></el-icon>
          </button>
          <div class="topbar-heading"><div class="breadcrumbs"><span>BrandPulse</span><el-icon><ArrowRight /></el-icon><span v-if="route.meta.group">{{ route.meta.group }}</span><el-icon v-if="route.meta.group"><ArrowRight /></el-icon><strong>{{ route.meta.title || '工作台' }}</strong></div><div class="topbar-title">{{ route.meta.title || '工作台' }}</div></div>
        </div>
        <div class="topbar-right">
          <ScopeSelector class="global-scope" />
          <DataFreshnessBadge class="topbar-freshness" :value="scopeStore.current?.latest_indicator_date" source="指标" />
          <el-button class="assistant-trigger" plain @click="assistantOpen = true"><el-icon><ChatDotRound /></el-icon><span>询问 BrandPulse</span></el-button>
          <el-dropdown trigger="click" @command="handleUserCommand">
            <button type="button" class="account-trigger" aria-label="账号菜单">
              <el-avatar :size="28" class="account-avatar"><el-icon><UserFilled /></el-icon></el-avatar>
              <span class="account-name">{{ userStore.user?.username || '未登录' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>{{ roleLabel }}</el-dropdown-item>
                <el-dropdown-item command="change-password">修改密码</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="content">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </el-main>
    </el-container>

    <button
      v-if="mobileSidebarOpen"
      type="button"
      class="sidebar-backdrop"
      aria-label="关闭导航菜单"
      @click="closeMobileSidebar"
    ></button>

    <div v-if="routeLoading" class="route-progress"></div>
    <AssistantDrawer v-model="assistantOpen" />
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { routeLoading } from './router'
import { useUserStore } from './stores/user'
import { useScopeStore } from './stores/scope'
import ScopeSelector from './components/ScopeSelector.vue'
import DataFreshnessBadge from './components/DataFreshnessBadge.vue'
import AssistantDrawer from './components/AssistantDrawer.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const scopeStore = useScopeStore()
const mobileSidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const assistantOpen = ref(false)
const isNarrow = ref(false)

const isBarePage = computed(() => ['/login', '/change-password'].includes(route.path))

const navGroups = [
  { path: '/', title: '工作台', icon: 'Odometer' },
  { id: 'insights', title: '品牌洞察', icon: 'Compass', items: [
    { path: '/brands', title: '品牌库', icon: 'Shop' },
    { path: '/opportunities', title: '机会雷达', icon: 'Radar' },
    { path: '/watchlist', title: '关注清单', icon: 'Star' },
  ] },
  { id: 'data', title: '数据中心', icon: 'DataAnalysis', items: [
    { path: '/data?tab=overview', title: '数据概览', icon: 'PieChart' },
    { path: '/data?tab=tables', title: '原始数据浏览', icon: 'Grid' },
    { path: '/data?tab=quality', title: '数据质量与匹配', icon: 'Finished' },
    { path: '/data?tab=lineage', title: '数据血缘', icon: 'Connection' },
  ] },
  { id: 'automation', title: '自动化中心', icon: 'Operation', items: [
    { path: '/automation?tab=collection', title: '采集计划', icon: 'Timer' },
    { path: '/automation?tab=alerts', title: '告警规则', icon: 'Bell' },
    { path: '/automation?tab=reports', title: '定时报告', icon: 'DocumentChecked' },
    { path: '/automation?tab=cases', title: '事项闭环', icon: 'Finished' },
    { path: '/automation?tab=runs', title: '运行与通知', icon: 'List' },
  ] },
  { id: 'settings', title: '系统设置', icon: 'Setting', items: [
    { path: '/formulas', title: '指标与公式', icon: 'MagicStick' },
    { path: '/users', title: '用户与权限', icon: 'UserFilled', permission: 'user.manage' },
    { path: '/audit', title: '操作审计', icon: 'Tickets', permission: 'audit.read' },
    { path: '/ml/forecasting', title: '实验室 · 预测', icon: 'TrendCharts' },
  ] },
]

const visibleGroups = computed(() => navGroups.map((group) => {
  if (!group.items) return group
  return { ...group, items: group.items.filter((item) => !item.permission || userStore.hasPermission(item.permission)) }
}).filter((group) => group.path || group.items.length))
const roleLabel = computed(() => ({ admin: '管理员', operator: '运营人员', viewer: '只读人员' }[userStore.user?.role] || '未登录'))
const sidebarWidth = computed(() => sidebarCollapsed.value ? '72px' : '232px')

const activeMenu = computed(() => {
  if (route.meta.navActive) return route.meta.navActive
  if (route.path === '/data') return `/data?tab=${route.query.tab || 'overview'}`
  if (route.path === '/automation') return `/automation?tab=${route.query.tab || 'collection'}`
  return route.path === '/dashboard' ? '/' : route.path
})

function toggleSidebar() {
  if (isNarrow.value) mobileSidebarOpen.value = !mobileSidebarOpen.value
  else sidebarCollapsed.value = !sidebarCollapsed.value
}

function closeMobileSidebar() {
  mobileSidebarOpen.value = false
}

async function handleUserCommand(command) {
  if (command === 'change-password') {
    router.push('/change-password')
    return
  }
  if (command === 'logout') {
    await userStore.logout()
    ElMessage.success('已退出登录')
    router.replace('/login')
  }
}

watch(() => route.path, closeMobileSidebar)
const media = window.matchMedia('(max-width: 767px)')
function syncViewport() {
  isNarrow.value = media.matches
  if (media.matches) sidebarCollapsed.value = false
  else mobileSidebarOpen.value = false
}
onMounted(() => { syncViewport(); media.addEventListener('change', syncViewport) })
onBeforeUnmount(() => media.removeEventListener('change', syncViewport))
</script>

<style scoped>
.layout {
  height: 100%;
}

.sidebar {
  background: var(--bp-sidebar-bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 0 0 auto;
  z-index: 1000;
  transition: width .18s ease;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 72px;
  padding: 18px 17px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.brand-text {
  display: flex;
  flex-direction: column;
}
.brand-name {
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.brand > .el-icon { flex: 0 0 auto; color: #74aaff; }
.sidebar.collapsed .brand { justify-content: center; padding-inline: 0; }
.sidebar.collapsed .brand-text, .sidebar.collapsed .sidebar-footer span { display: none; }
.brand-sub {
  color: #a6adb4;
  font-size: 11px;
  margin-top: 2px;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
  padding: 10px 8px;
  background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: transparent;
  --el-menu-text-color: #aebed0;
  --el-menu-active-color: #1e5fae;
}
.sidebar-menu :deep(.el-menu-item), .sidebar-menu :deep(.el-sub-menu__title) {
  height: 44px;
  margin: 2px 0;
  border-radius: 8px;
  color: #aebed0;
}
.sidebar-menu :deep(.el-sub-menu .el-menu-item) { min-width: 0; padding-left: 44px !important; font-size: 13px; }
.sidebar-menu :deep(.el-menu-item.is-active) {
  background: var(--bp-sidebar-active);
  color: #1e5fae;
  font-weight: 600;
}
.sidebar-menu :deep(.el-menu-item:hover), .sidebar-menu :deep(.el-sub-menu__title:hover) {
  background: rgba(255, 255, 255, .075);
  color: #fff;
}
.sidebar-menu :deep(.el-menu-item.is-active:hover) {
  background: var(--bp-sidebar-active);
  color: #1e5fae;
}
.sidebar-menu :deep(.el-menu-item .el-icon), .sidebar-menu :deep(.el-sub-menu__title .el-icon) { color: currentColor; }
.sidebar-menu :deep(.el-menu--inline) { background: transparent; }

.sidebar-footer {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 13px 16px;
  color: #8fa2b7;
  font-size: 11px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.main-wrap {
  min-width: 0;
}

.topbar {
  background: rgba(255, 255, 255, .94);
  border-bottom: 1px solid var(--bp-card-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.menu-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #53667b;
  cursor: pointer;
}
.menu-toggle:hover { background: #f1f5fa; }
.topbar-heading { min-width: 0; }
.breadcrumbs { display: flex; align-items: center; gap: 5px; color: #8a98a9; font-size: 11px; line-height: 1; }
.breadcrumbs strong { color: #5a6d82; font-weight: 600; }
.topbar-title {
  margin-top: 4px;
  color: var(--bp-text-strong);
  font-size: 15px;
  font-weight: 600;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #606266;
  font-size: 13px;
}
.account-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #303133;
  cursor: pointer;
}
.account-avatar { background: #e8f3ff; color: #409eff; }
.account-name { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.content {
  padding: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
}
.content > * {
  flex-shrink: 0;
}

.sidebar-backdrop {
  display: none;
}

@media (max-width: 767px) {
  .sidebar {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    width: 232px !important;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    box-shadow: 8px 0 24px rgba(0, 0, 0, 0.18);
  }

  .sidebar.sidebar-mobile-open {
    transform: translateX(0);
  }

  .topbar {
    padding: 0 12px;
  }

  .topbar-title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .topbar-heading .breadcrumbs, .global-scope, .topbar-freshness, .assistant-trigger span { display: none; }
  .assistant-trigger { min-width: 32px; padding-inline: 7px; }

  .account-name {
    display: none;
  }

  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 999;
    border: 0;
    background: rgba(0, 0, 0, 0.35);
  }
}
</style>
