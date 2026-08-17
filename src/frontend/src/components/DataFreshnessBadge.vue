<template>
  <el-tag class="freshness-badge" :type="tagType" effect="plain" size="small">
    <el-icon><component :is="tagIcon" /></el-icon>
    <span>{{ label }}</span>
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: [String, Date], default: '' },
  source: { type: String, default: '' },
  staleAfterHours: { type: Number, default: 72 },
  emptyText: { type: String, default: '数据未就绪' },
})

const parsed = computed(() => {
  if (!props.value) return null
  const raw = String(props.value)
  const date = new Date(raw.includes('T') ? raw : `${raw}T00:00:00`)
  return Number.isNaN(date.getTime()) ? null : date
})
const ageHours = computed(() => parsed.value ? (Date.now() - parsed.value.getTime()) / 36e5 : null)
const isStale = computed(() => ageHours.value !== null && ageHours.value > props.staleAfterHours)
const isDateOnly = computed(() => /^\d{4}-\d{2}-\d{2}$/.test(String(props.value || '')))
const tagType = computed(() => !parsed.value ? 'info' : isStale.value ? 'warning' : 'success')
const tagIcon = computed(() => !parsed.value ? 'InfoFilled' : isStale.value ? 'WarningFilled' : 'CircleCheckFilled')
const label = computed(() => {
  const prefix = props.source ? `${props.source}：` : ''
  if (!parsed.value) return `${prefix}${props.emptyText}`
  const date = isDateOnly.value
    ? String(props.value)
    : parsed.value.toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
  return `${prefix}${isStale.value ? '已过期' : '更新至'} ${date}`
})
</script>

<style scoped>
.freshness-badge { max-width: 100%; border-radius: 6px; font-weight: 500; }
.freshness-badge :deep(.el-tag__content) { display: inline-flex; align-items: center; gap: 4px; overflow: hidden; text-overflow: ellipsis; }
</style>
