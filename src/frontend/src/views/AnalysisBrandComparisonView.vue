<template>
  <div class="page analysis-page">
    <PageHeader title="品牌对比" description="选择 2～5 个真实品牌主数据进行比较；只有完成当前快照实体映射的品牌才会有可比值。">
      <template #actions><DataFreshnessBadge :value="analysis?.snapshot?.observed_at" source="快照" /><el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新</el-button></template>
    </PageHeader>

    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <div class="filter-field"><label>比较品牌</label><el-select v-model="selectedBrands" multiple collapse-tags collapse-tags-tooltip clearable placeholder="选择 2～5 个品牌" class="brand-select"><el-option v-for="brand in brands" :key="brand.id" :label="brand.name" :value="brand.id" /></el-select></div>
        <el-button type="primary" :disabled="selectedBrands.length < 2 || selectedBrands.length > 5" :loading="loading" @click="compare">开始对比</el-button>
        <el-button @click="clearSelection">清空</el-button>
      </div>
      <p class="filter-note">品牌库是主数据候选列表，不代表当前快照已有观测；未映射的品牌会保留为空，不会用主数据补造指标。</p>
    </el-card>

    <el-alert v-if="error" type="error" :closable="false" show-icon class="analysis-alert" :title="error"><el-button size="small" @click="load">重试</el-button></el-alert>
    <template v-if="analysis">
      <section class="context-strip"><div><span>范围</span><strong>{{ scopeLabel }}</strong></div><div><span>快照</span><strong>{{ analysis.snapshot.snapshot_id }}</strong></div><div><span>质量</span><el-tag :type="qualityType(analysis.snapshot.quality_grade)" effect="plain">{{ analysis.snapshot.quality_grade || '未评级' }}</el-tag></div></section>
      <el-alert v-if="analysis.warnings.length" type="warning" :closable="false" show-icon class="analysis-alert" title="对比数据边界"><ul class="warning-list"><li v-for="warning in analysis.warnings.slice(0, 5)" :key="warning">{{ warning }}</li></ul></el-alert>
      <el-card shadow="never" class="panel-card">
        <template #header><div class="panel-heading"><div><h2>品牌指标对比</h2><p>口碑和评价来自点评单源；小红书来源缺失时保持不可用。</p></div><el-tag type="info" effect="plain">{{ analysis.comparison.items.length }} 个有观测品牌</el-tag></div></template>
        <div v-if="analysis.comparison.items.length" class="table-scroll">
          <el-table :data="analysis.comparison.items" size="small">
            <el-table-column prop="brand_name" label="品牌" min-width="160" show-overflow-tooltip />
            <el-table-column label="贝叶斯口碑" width="130"><template #default="{ row }">{{ number(row.weighted_score, 2) }}</template></el-table-column>
            <el-table-column label="平均评分" width="110"><template #default="{ row }">{{ number(row.average_score, 2) }}</template></el-table-column>
            <el-table-column label="累计评价" width="120"><template #default="{ row }">{{ number(row.review_count) }}</template></el-table-column>
            <el-table-column label="点评评价份额" width="140"><template #default="{ row }">{{ percent(row.review_share) }}</template></el-table-column>
            <el-table-column label="门店观测" width="110"><template #default="{ row }">{{ number(row.store_count) }}</template></el-table-column>
            <el-table-column label="小红书内容" width="130"><template #default="{ row }">{{ nullableNumber(row.content_count) }}</template></el-table-column>
            <el-table-column label="数据状态" width="110"><template #default="{ row }"><el-tag :type="row.data_quality === 'valid' ? 'success' : 'warning'" effect="plain" size="small">{{ row.data_quality === 'valid' ? '可用' : '部分可用' }}</el-tag></template></el-table-column>
          </el-table>
        </div>
        <EmptyState v-else icon="Shop" title="暂无可比品牌观测" description="当前苏州中心·咖啡快照尚未完成品牌/门店确认映射，系统不会按品牌名称猜测归属。"><el-button type="primary" link @click="router.push('/data?tab=matching')">前往处理映射</el-button></EmptyState>
      </el-card>
    </template>
    <EmptyState v-else icon="Shop" title="选择品牌后开始对比" description="请先选择 2～5 个主数据品牌；结果是否可用取决于当前快照的真实映射状态。" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import DataFreshnessBadge from '../components/DataFreshnessBadge.vue'
import { fetchAnalysis } from '../api/analysis'
import { getBrands } from '../api/brands'
import { useScopeStore } from '../stores/scope'

const route = useRoute()
const router = useRouter()
const scopeStore = useScopeStore()
const brands = ref([])
const selectedBrands = ref(parseQueryBrands())
const analysis = ref(null)
const loading = ref(false)
const error = ref('')
const scopeLabel = computed(() => analysis.value?.scope ? [analysis.value.scope.city, analysis.value.scope.mall_name, analysis.value.scope.category].join(' · ') : scopeStore.label)

async function load() {
  loading.value = true; error.value = ''
  try {
    await scopeStore.load()
    if (route.query.scope_id && scopeStore.items.some((item) => item.scope_id === route.query.scope_id)) scopeStore.setCurrent(String(route.query.scope_id))
    const result = await getBrands({ page: 1, per_page: 100 })
    brands.value = result.items || []
    if (scopeStore.currentId) {
      syncUrl()
      analysis.value = await fetchAnalysis({ scope_id: scopeStore.currentId, view: 'comparison', brand_ids: selectedBrands.value.join(','), limit: 30 })
    }
  } catch (err) { error.value = String(err?.response?.data?.detail || err?.message || err) } finally { loading.value = false }
}
async function compare() {
  if (selectedBrands.value.length < 2 || selectedBrands.value.length > 5) return
  syncUrl()
  await loadAnalysis()
}
async function loadAnalysis() {
  if (!scopeStore.currentId) return
  loading.value = true
  try { analysis.value = await fetchAnalysis({ scope_id: scopeStore.currentId, view: 'comparison', brand_ids: selectedBrands.value.join(','), limit: 30 }) } catch (err) { error.value = String(err?.response?.data?.detail || err?.message || err) } finally { loading.value = false }
}
function syncUrl() { router.replace({ query: { ...route.query, scope_id: scopeStore.currentId, brands: selectedBrands.value.join(',') || undefined } }) }
function clearSelection() { selectedBrands.value = []; analysis.value = null; syncUrl() }
function parseQueryBrands() { return String(route.query.brands || '').split(',').map((item) => item.trim()).filter(Boolean).slice(0, 5) }
function number(value, digits = 0) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—' }
function nullableNumber(value) { return value === null || value === undefined ? '不可用' : number(value) }
function percent(value) { return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '—' }
function qualityType(value) { return ({ A: 'success', B: 'success', C: 'warning', D: 'danger', F: 'danger' })[value] || 'info' }
watch(() => scopeStore.currentId, (next, previous) => { if (next && next !== previous && !loading.value) load() })
onMounted(load)
</script>

<style scoped>
.analysis-page { min-width: 0; }
.filter-card { margin-bottom: 16px; }
.filter-row { display: flex; align-items: end; gap: 12px; flex-wrap: wrap; }
.filter-field { display: flex; min-width: min(460px, 100%); flex-direction: column; gap: 7px; }
.filter-field label { color: var(--bp-text-secondary); font-size: 12px; }
.brand-select { width: min(460px, 100%); }
.filter-note { margin: 10px 0 0; color: var(--bp-text-muted); font-size: 12px; line-height: 1.6; }
.analysis-alert { margin-bottom: 16px; }
.context-strip { display: grid; grid-template-columns: 1.5fr 2fr .7fr; gap: 1px; margin-bottom: 16px; overflow: hidden; border: 1px solid var(--bp-card-border); border-radius: var(--bp-radius-md); background: var(--bp-card-border); }
.context-strip > div { display: flex; min-width: 0; flex-direction: column; gap: 6px; padding: 13px 15px; background: var(--bp-surface); }
.context-strip span { color: var(--bp-text-muted); font-size: 12px; }
.context-strip strong { overflow: hidden; color: var(--bp-text-strong); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.panel-card { min-width: 0; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
h2 { margin: 0; color: var(--bp-text-strong); font-size: 16px; }
.panel-heading p { margin: 5px 0 0; color: var(--bp-text-muted); font-size: 12px; line-height: 1.5; }
.warning-list { margin: 0; padding-left: 18px; line-height: 1.7; }
@media (max-width: 600px) { .context-strip { grid-template-columns: 1fr; } .filter-field, .brand-select { width: 100%; min-width: 0; } }
</style>
