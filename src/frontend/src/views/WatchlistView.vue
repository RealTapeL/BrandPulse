<template>
  <div class="page watchlist-page">
    <PageHeader title="关注清单" description="将需要持续跟进的真实品牌主数据保存在当前浏览器，不会写入或伪造业务数据。"><template #actions><el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新</el-button><el-button v-if="items.length" text type="danger" @click="clear">清空关注</el-button></template></PageHeader>
    <el-alert class="watchlist-note" type="info" :closable="false" show-icon title="当前版本的关注清单仅保存在本浏览器。多用户共享关注、协作分配需要后端收藏接口支持。" />
    <div v-if="items.length" class="watchlist-grid"><el-card v-for="brand in items" :key="brand.id" shadow="never" class="watch-brand"><div class="watch-brand__head"><el-avatar :size="42" :src="brand.logo_url || undefined">{{ brand.name?.slice(0, 1) }}</el-avatar><div><h2>{{ brand.name }}</h2><p>{{ brand.category || '品类未维护' }} · {{ brand.city || '城市未维护' }}</p></div><el-tag :type="statusType(brand.status)" size="small">{{ statusLabel(brand.status) }}</el-tag></div><div class="watch-brand__foot"><span>最近采集：{{ brand.last_crawl_at ? formatTime(brand.last_crawl_at) : '暂无采集记录' }}</span><div><el-button link type="primary" @click="router.push(`/brands/${brand.id}`)">查看详情</el-button><el-button link type="danger" @click="remove(brand.id)">取消关注</el-button></div></div></el-card></div>
    <EmptyState v-else icon="Star" title="还没有关注品牌" description="在品牌详情页点击“加入关注”，即可将该品牌加入当前浏览器的关注清单。"><el-button type="primary" @click="router.push('/brands')">去品牌库选择</el-button></EmptyState>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import { getBrands } from '../api/brands'

const STORAGE_KEY = 'brandpulse.watchlist.brand-ids.v1'
const router = useRouter(); const items = ref([]); const loading = ref(false)
function ids() { try { const result = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); return Array.isArray(result) ? result.map(String) : [] } catch { return [] } }
function persist(value) { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)) }
async function load() { const selected = ids(); if (!selected.length) { items.value = []; return }; loading.value = true; try { const firstPage = await getBrands({ page: 1, per_page: 100 }); const pageCount = Math.ceil((firstPage.total || 0) / 100); const rest = await Promise.all(Array.from({ length: Math.max(0, pageCount - 1) }, (_, index) => getBrands({ page: index + 2, per_page: 100 }))); const records = [firstPage, ...rest].flatMap((result) => result.items || []); items.value = selected.map((id) => records.find((item) => String(item.id) === id)).filter(Boolean) } catch { items.value = [] } finally { loading.value = false } }
function remove(id) { persist(ids().filter((item) => item !== String(id))); load(); ElMessage.success('已取消关注') }
async function clear() { try { await ElMessageBox.confirm('确定清空当前浏览器中的关注清单吗？', '清空关注', { type: 'warning' }); persist([]); await load(); ElMessage.success('关注清单已清空') } catch {} }
function statusType(status) { return ({ active: 'success', crawling: 'warning', error: 'danger' })[status] || 'info' }; function statusLabel(status) { return ({ active: '正常', crawling: '采集中', error: '异常' })[status] || status || '未知' }; function formatTime(value) { return new Date(value).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) }
onMounted(load)
</script>

<style scoped>
.watchlist-note { margin-bottom: 16px; }.watchlist-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }.watch-brand__head { display: flex; align-items: center; gap: 10px; }.watch-brand__head > div { flex: 1; min-width: 0; }.watch-brand h2 { margin: 0; color: var(--bp-text-strong); font-size: 16px; }.watch-brand p { margin: 4px 0 0; color: var(--bp-text-muted); font-size: 12px; }.watch-brand__foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 18px; padding-top: 11px; border-top: 1px solid #edf1f5; color: var(--bp-text-muted); font-size: 12px; }.watch-brand__foot > div { white-space: nowrap; } @media (max-width: 1199px) { .watchlist-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } } @media (max-width: 767px) { .watchlist-grid { grid-template-columns: 1fr; }.watch-brand__foot { align-items: flex-start; flex-direction: column; } }
</style>
