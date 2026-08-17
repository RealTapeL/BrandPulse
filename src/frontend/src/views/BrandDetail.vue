<template>
  <div class="page brand-detail-page" v-loading="store.detailLoading">
    <template v-if="brand">
      <!-- 头部：品牌信息 + 操作 -->
      <div class="detail-header">
        <el-page-header aria-label="返回品牌列表" @back="router.back()">
          <template #content>
            <div class="header-brand">
              <el-avatar :size="40" :src="brand.logo_url || undefined">
                {{ brand.name.slice(0, 1) }}
              </el-avatar>
              <div>
                <div class="header-name">{{ brand.name }}</div>
                <div class="header-sub">{{ brand.category }} · {{ brand.city }}</div>
              </div>
            </div>
          </template>
        </el-page-header>
        <div class="detail-actions">
          <el-tag :type="trustedStatus.type" effect="plain">{{ trustedStatus.label }}</el-tag>
          <el-button plain @click="toggleWatch"><el-icon><Star /></el-icon>{{ watched ? '已关注' : '加入关注' }}</el-button>
          <el-button v-if="canCrawl" type="primary" aria-label="发起采集" :disabled="!scopeStore.currentId" @click="crawlDialog = true">按当前范围采集</el-button>
        </div>
      </div>

      <!-- 可信快照指标：只读当前范围中已确认映射的公开观测，不回退到历史热度字段。 -->
      <el-card class="section" shadow="never">
        <template #header>
          <div class="chart-head">
            <div><strong>当前范围可信公开观测</strong><p>{{ scopeStore.current ? `${scopeStore.label} · 仅展示已确认到该品牌的门店记录` : '请选择监测范围后查看快照数据' }}</p></div>
            <DataFreshnessBadge :value="trustedDashboard?.snapshot?.observed_at" source="快照" />
          </div>
        </template>
        <template v-if="trustedObservations.length">
          <el-alert type="info" :closable="false" show-icon title="以下是公开点评观测，不代表销售、坪效、租户健康度或自动招商结论。" />
          <div class="table-scroll trusted-table"><el-table :data="trustedObservations" size="small"><el-table-column prop="entity_name" label="已确认门店" min-width="220" /><el-table-column label="贝叶斯口碑" width="120"><template #default="{ row }">{{ number(row.weighted_score, 2) }}</template></el-table-column><el-table-column label="点评评价份额" width="135"><template #default="{ row }">{{ percent(row.sov) }}</template></el-table-column><el-table-column label="累计评价" width="120"><template #default="{ row }">{{ number(row.review_count) }}</template></el-table-column></el-table></div>
        </template>
        <el-empty v-else description="当前范围没有已确认映射到该品牌的可信公开观测。请先在数据中心核对原始记录，系统不会用名称猜测归属。" :image-size="72"><el-button type="primary" link @click="router.push('/data?tab=matching')">处理原始记录映射</el-button></el-empty>
      </el-card>

      <!-- 最近采集记录 -->
      <el-card class="section" shadow="never">
        <template #header>最近采集</template>
        <div class="table-scroll">
          <el-table :data="crawls" aria-label="最近采集记录">
          <el-table-column prop="job_id" label="任务 ID" width="140" />
          <el-table-column prop="mall" label="商场" min-width="120" />
          <el-table-column prop="category" label="品类" width="90" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="crawlStatusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="raw_saved" label="入库条数" width="100" />
          <el-table-column label="开始时间" width="180">
            <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
          </el-table-column>
          <template #empty><el-empty description="暂无采集记录" /></template>
          </el-table>
        </div>
      </el-card>

      <!-- 发起采集对话框 -->
      <el-dialog v-model="crawlDialog" title="按可信范围发起采集" width="min(480px, calc(100vw - 32px))">
        <el-alert type="info" :closable="false" show-icon title="采集会绑定当前城市 × 商场 × 品类范围。该品牌仅作为候选归属，结果不会自动确认实体映射。" />
        <el-descriptions class="crawl-scope" :column="1" border>
          <el-descriptions-item label="当前范围">{{ scopeStore.label }}</el-descriptions-item>
          <el-descriptions-item label="候选品牌">{{ brand.name }}</el-descriptions-item>
        </el-descriptions>
        <template #footer>
          <el-button @click="crawlDialog = false">取消</el-button>
          <el-button type="primary" :loading="crawling" aria-label="确认发起采集" @click="submitCrawl">
            开始采集
          </el-button>
        </template>
      </el-dialog>
    </template>

    <!-- 错误态：retry -->
    <el-result v-else-if="store.detailError" icon="error" title="品牌详情加载失败">
      <template #extra>
        <el-button type="primary" aria-label="重试加载品牌详情" @click="load">重试</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup>
/**
 * 品牌详情页 /brands/:id：品牌主数据、范围内可信公开观测、最近采集和候选采集。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useBrandsStore } from '../stores/brands'
import { usePermissions } from '../composables/usePermissions'
import { useScopeStore } from '../stores/scope'
import { fetchDashboard } from '../api/dashboard'
import DataFreshnessBadge from '../components/DataFreshnessBadge.vue'

const route = useRoute()
const router = useRouter()
const store = useBrandsStore()
const scopeStore = useScopeStore()
const { can } = usePermissions()
const canCrawl = can('crawl.execute')

const brandId = computed(() => String(route.params.id || ''))
const brand = computed(() => store.detail?.brand)
const crawls = computed(() => store.detail?.recent_crawls || [])
const trustedDashboard = ref(null)
const trustedObservations = computed(() => (trustedDashboard.value?.indicators || []).filter((item) => item.brand_id === brandId.value && item.entity_mapping_status === 'confirmed'))
const trustedStatus = computed(() => {
  if (!scopeStore.currentId) return { type: 'info', label: '未选择范围' }
  if (!trustedDashboard.value?.snapshot) return { type: 'warning', label: '快照未就绪' }
  return trustedObservations.value.length ? { type: 'success', label: '有可信公开观测' } : { type: 'warning', label: '映射未完成' }
})

const crawlDialog = ref(false)
const crawling = ref(false)
const WATCHLIST_KEY = 'brandpulse.watchlist.brand-ids.v1'
const watched = ref(false)

load()
watch(() => route.params.id, (next, previous) => {
  if (next && next !== previous) load(String(next))
})

async function load(id = brandId.value) {
  if (!id) return
  watched.value = getWatchedIds().includes(id)
  await Promise.all([store.fetchDetail(id), loadTrustedData()])
}

async function loadTrustedData() {
  await scopeStore.load()
  if (!scopeStore.currentId) { trustedDashboard.value = null; return }
  trustedDashboard.value = await fetchDashboard(scopeStore.currentId)
}

function getWatchedIds() {
  try {
    const value = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || '[]')
    return Array.isArray(value) ? value.map(String) : []
  } catch { return [] }
}

function toggleWatch() {
  const ids = getWatchedIds()
  const next = watched.value ? ids.filter((id) => id !== brandId.value) : [...new Set([...ids, brandId.value])]
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(next))
  watched.value = !watched.value
  ElMessage.success(watched.value ? '已加入当前浏览器的关注清单' : '已取消关注')
}

async function submitCrawl() {
  if (!scopeStore.currentId) {
    ElMessage.warning('请先在顶部选择可信监测范围')
    return
  }
  crawling.value = true
  try {
    const { job_id } = await store.crawl(brandId.value, {
      scope_id: scopeStore.currentId,
    })
    ElMessage.info(`采集任务已入队：${job_id}`)
    crawlDialog.value = false
    await pollCrawlJob(job_id)
  } catch {
    // 错误提示由 axios 拦截器统一弹出
  } finally {
    crawling.value = false
  }
}

async function pollCrawlJob(jobId) {
  const maxPolls = 90
  for (let index = 0; index < maxPolls; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    const job = await store.fetchCrawlJob(jobId)
    if (job.status === 'completed') {
      await load()
      ElMessage.success(`采集完成：入库 ${job.result ? '结果已写回' : '暂无结果摘要'}`)
      return
    }
    if (job.status === 'failed') {
      await load()
      ElMessage.error('采集任务失败，请查看最近采集记录')
      return
    }
  }
  ElMessage.warning('采集仍在后台执行，可稍后刷新页面查看结果')
}

function crawlStatusType(s) {
  return { success: 'success', running: 'warning', failed: 'danger' }[s] || 'info'
}
function number(value, digits = 0) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '-' }
function percent(value) { return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '-' }

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}
watch(() => scopeStore.currentId, () => { loadTrustedData().catch(() => {}) })
</script>

<style scoped>
.brand-detail-page {
  min-width: 0;
}
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}
.detail-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.header-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-name {
  font-size: 16px;
  font-weight: 600;
}
.header-sub {
  color: #909399;
  font-size: 12px;
  margin-top: 2px;
}
.section {
  margin-bottom: 16px;
}
.crawl-scope { margin-top: 16px; }
.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

@media (max-width: 767px) {
  .detail-header :deep(.el-page-header) {
    width: 100%;
  }

  .detail-actions,
  .detail-actions > .el-button {
    width: 100%;
  }
}
</style>
