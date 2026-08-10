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
        <el-button type="primary" aria-label="发起采集" @click="crawlDialog = true">发起采集</el-button>
      </div>

      <!-- 指标趋势图 -->
      <el-card class="section" shadow="never">
        <template #header>
          <div class="chart-head">
            <span>{{ indicatorLabel }}趋势（近 30 个数据期）</span>
            <el-select v-model="indicator" size="small" class="indicator-select" @change="loadIndicator">
              <el-option label="热度指数" value="heat" />
              <el-option label="口碑分" value="reputation" />
              <el-option label="SOV 声量份额" value="sov" />
              <el-option label="周环比动量" value="momentum" />
              <el-option label="波动率" value="volatility" />
            </el-select>
          </div>
        </template>
        <EChart :option="chartOption" height="320px" />
        <el-empty v-if="!indicatorLoading && !indicatorSeries.length" description="该品牌尚无已确认归属的真实指标数据" :image-size="72" />
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
      <el-dialog v-model="crawlDialog" title="发起采集" width="min(420px, calc(100vw - 32px))">
        <el-form label-position="top">
          <el-form-item label="商场">
            <el-input v-model="crawlForm.mall" aria-label="商场名" placeholder="如：苏州中心" />
          </el-form-item>
          <el-form-item label="品类">
            <el-input v-model="crawlForm.category" aria-label="品类" placeholder="如：咖啡" />
          </el-form-item>
          <el-form-item label="城市（逗号分隔，可空）">
            <el-input v-model="crawlForm.citiesText" aria-label="城市列表" placeholder="如：苏州" />
          </el-form-item>
        </el-form>
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
 * 品牌详情页 /brands/:id：品牌信息、可切换指标趋势、最近采集记录和发起采集。
 */
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import EChart from '../components/EChart.vue'
import { useBrandsStore } from '../stores/brands'
import { getBrandIndicatorSeries } from '../api/brands'

const route = useRoute()
const router = useRouter()
const store = useBrandsStore()

const brandId = computed(() => String(route.params.id || ''))
const brand = computed(() => store.detail?.brand)
const crawls = computed(() => store.detail?.recent_crawls || [])
const indicator = ref('heat')
const indicatorSeries = ref([])
const indicatorLoading = ref(false)
let indicatorRequestId = 0
const indicatorLabels = { heat: '热度指数', reputation: '口碑分', sov: 'SOV 声量份额', momentum: '周环比动量', volatility: '波动率' }
const indicatorLabel = computed(() => indicatorLabels[indicator.value] || indicator.value)

const crawlDialog = ref(false)
const crawling = ref(false)
const crawlForm = reactive({ mall: '苏州中心', category: '咖啡', citiesText: '苏州' })

load()
watch(() => route.params.id, (next, previous) => {
  if (next && next !== previous) load(String(next))
})

function load(id = brandId.value) {
  if (!id) return
  store.fetchDetail(id)
  loadIndicator(id)
}

async function loadIndicator(id = brandId.value) {
  if (!id) return
  const requestId = ++indicatorRequestId
  indicatorLoading.value = true
  try {
    const result = await getBrandIndicatorSeries(id, indicator.value)
    if (requestId === indicatorRequestId && id === brandId.value) indicatorSeries.value = result.series || []
  } finally {
    if (requestId === indicatorRequestId) indicatorLoading.value = false
  }
}

const chartOption = computed(() => {
  const series = indicatorSeries.value
  return {
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: series.map((p) => p.date) },
    yAxis: { type: 'value', name: indicatorLabel.value },
    series: [
      {
        name: indicatorLabel.value,
        type: 'line',
        smooth: true,
        data: series.map((p) => p.value),
        areaStyle: { opacity: 0.12 },
      },
    ],
  }
})

async function submitCrawl() {
  crawling.value = true
  try {
    const cities = crawlForm.citiesText
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean)
    const { job_id } = await store.crawl(brandId.value, {
      mall: crawlForm.mall,
      category: crawlForm.category,
      cities: cities.length ? cities : undefined,
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

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}
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
.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.indicator-select {
  width: 150px;
}

@media (max-width: 767px) {
  .detail-header :deep(.el-page-header) {
    width: 100%;
  }

  .detail-header > .el-button,
  .indicator-select {
    width: 100%;
  }
}
</style>
