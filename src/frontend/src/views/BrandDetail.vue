<template>
  <div class="brand-detail-page" v-loading="store.detailLoading">
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
        <template #header>热度指数趋势（近 30 天）</template>
        <EChart :option="chartOption" height="320px" />
      </el-card>

      <!-- 最近采集记录 -->
      <el-card class="section" shadow="never">
        <template #header>最近采集</template>
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
      </el-card>

      <!-- 发起采集对话框 -->
      <el-dialog v-model="crawlDialog" title="发起采集" width="420px">
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
 * 品牌详情页 /brands/:id：品牌信息 + 指标趋势（ECharts）+ 最近采集记录 + 发起采集。
 * TODO: 指标种类切换（口碑/热度/SOV）待后端 /api/v1/indicators 就绪后接入。
 */
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import EChart from '../components/EChart.vue'
import { useBrandsStore } from '../stores/brands'

const route = useRoute()
const router = useRouter()
const store = useBrandsStore()

const brandId = route.params.id
const brand = computed(() => store.detail?.brand)
const crawls = computed(() => store.detail?.recent_crawls || [])

const crawlDialog = ref(false)
const crawling = ref(false)
const crawlForm = reactive({ mall: '苏州中心', category: '咖啡', citiesText: '苏州' })

load()

function load() {
  store.fetchDetail(brandId)
}

const chartOption = computed(() => {
  const series = store.detail?.stats?.indicators || []
  return {
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: series.map((p) => p.date) },
    yAxis: { type: 'value', name: '热度指数' },
    series: [
      {
        name: '热度指数',
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
    const { job_id } = await store.crawl(brandId, {
      mall: crawlForm.mall,
      category: crawlForm.category,
      cities: cities.length ? cities : undefined,
    })
    ElMessage.success(`采集任务已发起：${job_id}`)
    crawlDialog.value = false
  } catch {
    // 错误提示由 axios 拦截器统一弹出
  } finally {
    crawling.value = false
  }
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
  padding: 20px;
}
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
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
</style>
