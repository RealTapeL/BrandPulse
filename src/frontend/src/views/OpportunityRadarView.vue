<template>
  <div class="page opportunity-page">
    <PageHeader title="机会雷达" :description="description">
      <template #actions><el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新</el-button></template>
    </PageHeader>
    <el-card shadow="never" class="filter-card"><div class="radar-filters"><span>机会类型</span><el-radio-group v-model="filter"><el-radio-button label="all">全部</el-radio-button><el-radio-button label="机会">机会</el-radio-button><el-radio-button label="风险">风险</el-radio-button><el-radio-button label="信号">信号</el-radio-button><el-radio-button label="数据问题">数据问题</el-radio-button></el-radio-group><DataFreshnessBadge :value="response?.snapshot?.observed_at" source="指标快照" /></div></el-card>
    <el-alert v-if="error" class="load-error" type="error" :closable="false" show-icon :title="error"><template #default><el-button size="small" @click="load">重试</el-button></template></el-alert>
    <div v-if="loading && !response" class="radar-grid"><el-skeleton v-for="n in 4" :key="n" animated :rows="4" /></div>
    <div v-else-if="filteredItems.length" class="radar-grid"><el-card v-for="item in filteredItems" :key="item.signal_id" shadow="never" class="radar-card"><div class="radar-card__top"><el-tag :type="tagType(item.type)" effect="plain">{{ item.type }}</el-tag><span>{{ item.lifecycle_status }}</span></div><h2>{{ item.entity_name }}</h2><p>{{ item.trigger_rule }}</p><div class="radar-card__evidence"><span>快照：{{ item.snapshot_id }}</span><span>质量：{{ item.quality_grade }}</span><span v-if="item.confidence !== null && item.confidence !== undefined">置信度：{{ Math.round(item.confidence * 100) }}%</span></div><div class="radar-card__footer"><span>{{ item.recommended_action || '请先查看证据并人工确认。' }}</span><el-button link type="primary" @click="takeAction(item)">{{ actionLabel(item) }}</el-button></div></el-card></div>
    <EmptyState v-else icon="Compass" title="暂无符合条件的机会信号" :description="emptyDescription"><el-button type="primary" link @click="router.push('/data?tab=overview')">查看数据就绪情况</el-button></EmptyState>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import DataFreshnessBadge from '../components/DataFreshnessBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import { useScopeStore } from '../stores/scope'
import { fetchOpportunities, updateOpportunity } from '../api/opportunities'
import { createCaseFromSource } from '../api/cases'
import { usePermissions } from '../composables/usePermissions'

const router = useRouter(); const scopeStore = useScopeStore(); const response = ref(null); const loading = ref(false); const error = ref(''); const filter = ref('all'); const { can } = usePermissions(); const canManage = can('opportunity.manage'); const canManageCases = can('case.manage')
const description = computed(() => scopeStore.current ? `${scopeStore.label} 的机会、风险与数据就绪信号。只根据当前可用数据生成。` : '请选择监测范围后查看机会信号。')
const items = computed(() => (response.value?.items || []).map((item) => ({ ...item, type: ({ opportunity: '机会', risk: '风险', data_quality: '数据问题', information: '信号' })[item.signal_class] || '信号' })))
const filteredItems = computed(() => filter.value === 'all' ? items.value : items.value.filter((item) => item.type === filter.value))
const emptyDescription = computed(() => response.value?.snapshot ? '当前可信快照没有触发所选规则；这不代表未来没有机会。' : '当前范围缺少可发布快照，尚不能可靠判断品牌机会。')
function tagType(type) { return ({ 机会: 'success', 风险: 'warning', 信号: 'info', 数据问题: 'danger' })[type] || 'info' }
function actionLabel(item) { if (item.signal_class === 'data_quality') return canManageCases.value ? '创建治理事项' : (item.signal_type === 'data_mapping_incomplete' ? '处理映射' : '查看快照'); return canManage.value ? '推进线索' : '查看品牌' }
async function takeAction(item) { if (item.signal_class === 'data_quality') { if (canManageCases.value) { const result = await createCaseFromSource({ source_type: 'opportunity_signal', source_id: item.signal_id }); ElMessage.success(result.reused ? '已有开放事项，已避免重复创建' : '已创建数据治理事项'); router.push('/automation?tab=cases'); return }; router.push(item.signal_type === 'data_mapping_incomplete' ? '/data?tab=matching' : '/data?tab=snapshots'); return }; if (!canManage.value) { router.push(item.brand_id ? `/brands/${item.brand_id}` : '/brands'); return }; try { const { value } = await ElMessageBox.prompt('记录本次判断或下一步动作（可留空）', '推进招商线索', { inputPlaceholder: '例如：已核对品牌定位，安排补充资料', inputValue: item.human_comment || '', confirmButtonText: '进入复核', cancelButtonText: '取消' }); await updateOpportunity(item.signal_id, { lifecycle_status: 'under_review', owner_id: '', human_comment: value || '', human_confirmed: true }); await createCaseFromSource({ source_type: 'opportunity_signal', source_id: item.signal_id }); ElMessage.success('已推进线索并创建待处理事项'); await load() } catch {} }
async function load() { loading.value = true; error.value = ''; try { await scopeStore.load(); if (!scopeStore.currentId) { response.value = null; return }; response.value = await fetchOpportunities({ scopeId: scopeStore.currentId }) } catch (err) { error.value = `机会雷达加载失败：${err?.response?.data?.detail || err?.message || err}` } finally { loading.value = false } }
watch(() => scopeStore.currentId, () => { if (!loading.value) load() }); onMounted(load)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }.radar-filters { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; color: var(--bp-text-secondary); font-size: 13px; }.radar-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }.radar-card { min-height: 216px; }.radar-card__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--bp-text-muted); font-size: 12px; }.radar-card h2 { margin: 17px 0 7px; color: var(--bp-text-strong); font-size: 17px; }.radar-card p { min-height: 58px; margin: 0; color: var(--bp-text-secondary); font-size: 13px; line-height: 1.65; }.radar-card__evidence { display: flex; flex-wrap: wrap; gap: 5px 10px; margin-top: 11px; color: var(--bp-text-muted); font-size: 11px; }.radar-card__footer { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-top: 14px; padding-top: 11px; border-top: 1px solid #edf1f5; color: var(--bp-text-muted); font-size: 11px; line-height: 1.55; }.radar-card__footer > span { flex: 1; }.load-error { margin-bottom: 16px; } @media (max-width: 1199px) { .radar-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } } @media (max-width: 767px) { .radar-grid { grid-template-columns: 1fr; }.radar-filters { align-items: flex-start; flex-direction: column; }.radar-filters :deep(.el-radio-group) { display: flex; flex-wrap: wrap; } }
</style>
