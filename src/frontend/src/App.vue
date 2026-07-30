<template>
  <el-container class="layout">
    <!-- 左侧深色侧边栏 -->
    <el-aside width="216px" class="sidebar">
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
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">数据范围：苏州中心 · 咖啡品类</div>
    </el-aside>

    <el-container class="main-wrap">
      <!-- 顶部栏 -->
      <el-header class="topbar" height="56px">
        <div class="topbar-title">{{ route.meta.title || '数据看板' }}</div>
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

    <div v-if="routeLoading" class="route-progress"></div>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { routeLoading } from './router'

const route = useRoute()

const menus = [
  { path: '/', title: '数据看板', icon: 'Odometer' },
  { path: '/chat', title: '对话助手', icon: 'ChatDotRound' },
  { path: '/tables', title: '数据表查看', icon: 'Grid' },
  { path: '/formulas', title: '指标公式管理', icon: 'MagicStick' },
]

const activeMenu = computed(() => route.path)

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
  display: flex;
  flex-direction: column;
}
.content > * {
  flex-shrink: 0;
}
</style>
