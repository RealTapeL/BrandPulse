<template>
  <el-select
    v-model="scopeId"
    class="scope-selector"
    :loading="scopeStore.loading"
    :disabled="!scopeStore.items.length && scopeStore.loading"
    placeholder="选择监测范围"
    aria-label="全局监测范围"
    @visible-change="loadWhenOpen"
  >
    <template #prefix><el-icon><Location /></el-icon></template>
    <el-option v-for="scope in scopeStore.items" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" />
    <template #empty><el-empty :image-size="44" description="暂无已登记监测范围" /></template>
  </el-select>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useScopeStore } from '../stores/scope'

const scopeStore = useScopeStore()
const scopeId = computed({
  get: () => scopeStore.currentId,
  set: (value) => scopeStore.setCurrent(value),
})

function scopeLabel(scope) {
  return [scope.city, scope.mall_name, scope.category].filter(Boolean).join(' · ') || scope.scope_id
}
function loadWhenOpen(open) {
  if (open && !scopeStore.loaded) scopeStore.load().catch(() => {})
}
onMounted(() => scopeStore.load().catch(() => {}))
</script>

<style scoped>
.scope-selector { width: 276px; }
@media (max-width: 1023px) { .scope-selector { width: 224px; } }
@media (max-width: 767px) { .scope-selector { width: 100%; } }
</style>
