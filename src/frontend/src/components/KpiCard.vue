<template>
  <el-card shadow="never" class="kpi-card">
    <div class="kpi-card__head"><span>{{ label }}</span><el-icon v-if="icon"><component :is="icon" /></el-icon></div>
    <div class="kpi-card__value">{{ value }}</div>
    <div class="kpi-card__foot">
      <span class="kpi-card__note">{{ note || '暂无可比周期' }}</span>
      <DataFreshnessBadge v-if="updatedAt" :value="updatedAt" :source="source" />
    </div>
  </el-card>
</template>

<script setup>
import DataFreshnessBadge from './DataFreshnessBadge.vue'
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '-' },
  note: { type: String, default: '' },
  updatedAt: { type: [String, Date], default: '' },
  source: { type: String, default: '' },
  icon: { type: String, default: '' },
})
</script>

<style scoped>
.kpi-card { height: 100%; border: 1px solid var(--bp-card-border); }
.kpi-card :deep(.el-card__body) { padding: 17px 18px; }
.kpi-card__head { display: flex; align-items: center; justify-content: space-between; color: var(--bp-text-muted); font-size: 13px; }
.kpi-card__head .el-icon { color: var(--bp-primary); font-size: 17px; }
.kpi-card__value { margin: 10px 0 12px; color: var(--bp-text-strong); font-size: 28px; font-weight: 700; line-height: 1.1; letter-spacing: -.03em; }
.kpi-card__foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.kpi-card__note { overflow: hidden; color: var(--bp-text-muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.kpi-card__foot :deep(.freshness-badge) { flex: 0 0 auto; max-width: 105px; }
.kpi-card__foot :deep(.freshness-badge .el-tag__content) { white-space: nowrap; }
</style>
