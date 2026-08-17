<template>
  <div class="empty-state">
    <el-icon :size="32"><component :is="icon" /></el-icon>
    <strong>{{ title }}</strong>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  icon: { type: String, default: 'DataAnalysis' },
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
})
</script>

<style scoped>
.empty-state { display: flex; min-height: 180px; align-items: center; justify-content: center; flex-direction: column; padding: 24px; color: var(--bp-text-muted); text-align: center; }
.empty-state .el-icon { margin-bottom: 10px; color: #aebdce; }
strong { color: var(--bp-text-secondary); font-size: 14px; }
p { max-width: 420px; margin: 6px 0 0; font-size: 12px; line-height: 1.6; }
</style>
