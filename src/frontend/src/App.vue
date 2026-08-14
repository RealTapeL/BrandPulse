<template>
  <!-- 登录页：全屏裸布局，不带侧边栏 -->
  <router-view v-if="isLoginPage" />
  <el-container v-else class="layout">
    <!-- 左侧深色侧边栏 -->
    <el-aside width="216px" class="sidebar" :class="{ 'sidebar-mobile-open': mobileSidebarOpen }">
      <div class="brand">
        <el-icon :size="22" color="#409eff"><DataAnalysis /></el-icon>
        <div class="brand-text">
          <span class="brand-name">BrandPulse</span>
          <span class="brand-sub">招商品牌情报平台</span>
        </div>
      </div>
      <el-menu
        class="sidebar-menu"
        :default-active="activeMenu"
        background-color="#001529"
        text-color="#a6adb4"
        active-text-color="#ffffff"
        router
        @select="closeMobileSidebar"
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">数据范围由看板项目 / 品类选择器确定</div>
    </el-aside>

    <el-container class="main-wrap">
      <!-- 顶部栏 -->
      <el-header class="topbar" height="56px">
        <div class="topbar-left">
          <button type="button" class="menu-toggle" aria-label="打开导航菜单" @click="toggleMobileSidebar">
            <el-icon :size="20"><Expand /></el-icon>
          </button>
          <div class="topbar-title">{{ route.meta.title || '数据看板' }}</div>
        </div>
        <div class="topbar-right">
          <el-icon color="#909399"><Calendar /></el-icon>
          <span>{{ today }}</span>
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
  </el-container>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { routeLoading } from './router'

const route = useRoute()
const mobileSidebarOpen = ref(false)

const isLoginPage = computed(() => route.path === '/login')

const menus = [
  { path: '/', title: '数据看板', icon: 'Odometer' },
  { path: '/brands', title: '品牌列表', icon: 'Shop' },
  { path: '/agent/console', title: 'Agent 控制台', icon: 'Cpu' },
  { path: '/chat', title: '对话助手', icon: 'ChatDotRound' },
  { path: '/tables', title: '数据表查看', icon: 'Grid' },
  { path: '/formulas', title: '指标公式管理', icon: 'MagicStick' },
  { path: '/data-governance', title: '数据治理', icon: 'Finished' },
  { path: '/ml/forecasting', title: '机器学习预测', icon: 'TrendCharts' },
  { path: '/monitoring', title: '自动监控与告警', icon: 'Bell' },
  { path: '/reports', title: '自动报告与导出', icon: 'DocumentChecked' },
  { path: '/audit', title: '操作审计', icon: 'Tickets' },
]

const activeMenu = computed(() => {
  const path = route.path === '/dashboard' ? '/' : route.path
  if (path === '/') return '/'
  return menus.find((item) => item.path !== '/' && path.startsWith(item.path))?.path || path
})

function toggleMobileSidebar() {
  mobileSidebarOpen.value = !mobileSidebarOpen.value
}

function closeMobileSidebar() {
  mobileSidebarOpen.value = false
}

watch(() => route.path, closeMobileSidebar)

const today = new Date().toLocaleDateString('zh-CN', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'long',
})
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
  flex: 0 0 216px;
  z-index: 1000;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
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
.brand-sub {
  color: #a6adb4;
  font-size: 11px;
  margin-top: 2px;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
  padding-top: 8px;
}
.sidebar-menu :deep(.el-menu-item) {
  height: 46px;
  margin: 2px 8px;
  border-radius: 6px;
}
.sidebar-menu :deep(.el-menu-item.is-active) {
  background: var(--bp-sidebar-active);
}
.sidebar-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
}
.sidebar-menu :deep(.el-menu-item.is-active:hover) {
  background: var(--bp-sidebar-active);
}

.sidebar-footer {
  padding: 12px 16px;
  color: #5c6470;
  font-size: 11px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.main-wrap {
  min-width: 0;
}

.topbar {
  background: #fff;
  border-bottom: 1px solid var(--bp-card-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.menu-toggle {
  display: none;
  border: 0;
  background: transparent;
  color: #606266;
  padding: 4px;
  cursor: pointer;
}
.topbar-title {
  font-size: 16px;
  font-weight: 600;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
  font-size: 13px;
}

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
    width: 216px !important;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    box-shadow: 8px 0 24px rgba(0, 0, 0, 0.18);
  }

  .sidebar.sidebar-mobile-open {
    transform: translateX(0);
  }

  .menu-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .topbar {
    padding: 0 12px;
  }

  .topbar-title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .topbar-right span {
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
