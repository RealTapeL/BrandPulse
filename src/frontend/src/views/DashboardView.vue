<template>
  <div class="page">
    <div class="page-header">
      <h2>数据看板</h2>
      <p class="desc" v-if="data">
        指标日期：{{ data.stat_date || '-' }}　·　点评采集日：{{ data.crawl_date || '-' }}　·　数据范围：{{ scopeLabel(data.scope) }}
      </p>
    </div>

    <el-card shadow="never" class="scope-card">
      <div class="scope-bar">
        <span class="scope-label">监测项目 / 品类</span>
        <el-select v-model="scopeId" :loading="scopesLoading" class="scope-select" @change="load">
          <el-option v-for="scope in scopes" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" />
        </el-select>
        <span v-if="data?.scope" class="scope-meta">
          来源：{{ data.scope.data_origin }} · 指标 {{ data.scope.latest_indicator_date || '未生成' }}
        </span>
      </div>
    </el-card>

    <!-- 加载态 -->
    <el-card v-if="loading" shadow="never">
      <el-skeleton :rows="8" animated />
    </el-card>

    <!-- 错误态 -->
    <el-card v-else-if="error" shadow="never">
      <el-result icon="error" title="看板数据加载失败" :sub-title="error">
        <template #extra>
          <el-button type="primary" :loading="loading" @click="reload">重新加载</el-button>
        </template>
      </el-result>
    </el-card>

    <template v-else-if="data">
      <!-- KPI 卡片 -->
      <el-row :gutter="16" class="kpi-row">
        <el-col v-for="kpi in kpis" :key="kpi.label" :xs="12" :sm="12" :md="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-label">
              <el-icon :color="kpi.color"><component :is="kpi.icon" /></el-icon>
              <span>{{ kpi.label }}</span>
            </div>
            <div class="kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}</div>
            <div class="kpi-sub">{{ kpi.sub }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 指标口径说明 -->
      <h3 class="section-title">指标口径说明</h3>
      <el-card shadow="never">
        <div class="table-scroll">
          <el-table :data="metricDocs" border stripe>
          <el-table-column label="指标" width="140">
            <template #default="{ row }">
              <el-link type="primary" underline="never" @click="scrollToChart(row.anchor)">
                {{ row.name }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="method" label="计算方法" min-width="300" />
          <el-table-column prop="meaning" label="解读" min-width="320" />
          </el-table>
        </div>
      </el-card>

      <template v-if="data.indicators.length">
        <!-- 四象限气泡图 -->
        <h3 class="section-title">四象限气泡图</h3>
        <el-card shadow="never" :id="ANCHOR.quadrant" class="anchor-card">
          <EChart :option="quadrantOption" height="420px" />
        </el-card>

        <!-- 口碑 / 热度 / SOV -->
        <el-row :gutter="16">
          <el-col :xs="24" :md="12">
            <h3 class="section-title">门店口碑分对比</h3>
            <el-card shadow="never" :id="ANCHOR.wom" class="anchor-card">
              <EChart :option="womOption" />
            </el-card>
          </el-col>
          <el-col :xs="24" :md="12">
            <h3 class="section-title">门店热度指数对比</h3>
            <el-card shadow="never" :id="ANCHOR.heat" class="anchor-card">
              <EChart :option="heatOption" />
            </el-card>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :xs="24" :md="12">
            <h3 class="section-title">门店评分对比</h3>
            <el-card shadow="never" class="anchor-card">
              <EChart :option="scoreOption" />
            </el-card>
          </el-col>
          <el-col :xs="24" :md="12">
            <h3 class="section-title">SOV 声量份额</h3>
            <el-card shadow="never" :id="ANCHOR.sov" class="anchor-card">
              <EChart :option="sovOption" />
            </el-card>
          </el-col>
        </el-row>
      </template>

      <!-- 小红书点赞 Top10 -->
      <template v-if="data.xhs_notes.length">
        <h3 class="section-title">小红书点赞 Top10</h3>
        <el-card shadow="never">
          <EChart :option="xhsOption" />
        </el-card>
      </template>

      <!-- 明细表 -->
      <h3 class="section-title">大众点评门店明细</h3>
      <el-card shadow="never">
        <div class="table-scroll">
          <el-table :data="data.dp_shops" border stripe max-height="420"
                    :empty-text="'暂无门店数据'">
          <el-table-column prop="shop_name" label="门店" min-width="220" show-overflow-tooltip />
          <el-table-column prop="score" label="评分" width="90" sortable />
          <el-table-column prop="review_count" label="评价数" width="100" sortable />
          <el-table-column prop="avg_price" label="人均(元)" width="100" sortable />
          <el-table-column label="商圈" min-width="130">
            <template #default="{ row }">{{ row.business_area || '-' }}</template>
          </el-table-column>
          <el-table-column label="位置" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.place || '-' }}</template>
          </el-table-column>
          </el-table>
        </div>
      </el-card>

      <h3 class="section-title">小红书笔记明细（按点赞降序）</h3>
      <el-card shadow="never">
        <div class="table-scroll">
          <el-table :data="data.xhs_notes" border stripe max-height="420"
                    :empty-text="'暂无笔记数据'">
          <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
          <el-table-column prop="author_name" label="作者" width="140" />
          <el-table-column prop="likes" label="点赞" width="90" sortable />
          <el-table-column label="发布时间" width="150">
            <template #default="{ row }">{{ row.publish_time || '-' }}</template>
          </el-table-column>
          </el-table>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import EChart from '../components/EChart.vue'
import { fetchDashboard, fetchDashboardScopes } from '../api/dashboard'
import {
  buildQuadrantOption,
  buildScoreOption,
  buildWomOption,
  buildHeatOption,
  buildSovOption,
  buildXhsOption,
} from '../components/dashboard/chartOptions'

// hash 路由下不能用 #anchor 跳转，改为 JS 滚动到卡片
const ANCHOR = { wom: 'chart-wom', heat: 'chart-heat', sov: 'chart-sov', quadrant: 'chart-quadrant' }

const metricDocs = [
  {
    name: '口碑分',
    anchor: ANCHOR.wom,
    method: '贝叶斯加权 WR = (v/(v+m))·R + (m/(v+m))·C',
    meaning: '评价数 v 越少越向全局均值 C 收缩，避免小样本门店分数虚高（0~5 分）',
  },
  {
    name: '热度指数',
    anchor: ANCHOR.heat,
    method: '100·ln(1+v)/ln(1+50000)，v 为点评评价数',
    meaning: '对数压缩长尾，5 万评价视为满分热度（0~100），固定基准保证跨天可比',
  },
  {
    name: 'SOV 声量份额',
    anchor: ANCHOR.sov,
    method: '门店评价数 ÷ 同商场总评价数',
    meaning: '衡量门店在当前项目/品类范围内的声量占比（0~1）',
  },
  {
    name: '四象限图',
    anchor: ANCHOR.quadrant,
    method: 'X = 口碑分，Y = 热度指数，气泡大小 = SOV',
    meaning: '右上为「高口碑高热度」优质品牌；左下为待观察对象',
  },
]

const data = ref(null)
const scopes = ref([])
const scopeId = ref('')
const scopesLoading = ref(false)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchDashboard(scopeId.value)
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    loading.value = false
  }
}

async function loadScopes() {
  scopesLoading.value = true
  try {
    const result = await fetchDashboardScopes()
    scopes.value = result.items || []
    if (!scopeId.value && scopes.value.length) {
      scopeId.value = scopes.value.find((item) => item.latest_indicator_date)?.scope_id || scopes.value[0].scope_id
    }
  } catch (e) {
    error.value = String(e.message || e)
  } finally {
    scopesLoading.value = false
  }
}

async function reload() {
  await loadScopes()
  if (!error.value) await load()
}

function scopeLabel(scope) {
  if (!scope) return '未选择范围'
  return `${scope.city || '-'} · ${scope.mall_name || '-'} · ${scope.category || '-'}`
}

onMounted(async () => {
  await reload()
})

const kpis = computed(() => {
  const d = data.value
  if (!d) return []
  const ind = d.indicators
  const avgScore = ind.length ? (ind.reduce((s, r) => s + r.weighted_score, 0) / ind.length).toFixed(2) : '-'
  const hottest = ind.length ? ind.reduce((a, b) => (b.heat_index > a.heat_index ? b : a)) : null
  const totalLikes = d.xhs_notes.reduce((s, n) => s + (n.likes || 0), 0)
  return [
    { label: '监测门店数', value: d.dp_shops.length, sub: '点评最新采集日', icon: 'Shop', color: '#409eff' },
    { label: '平均口碑分', value: avgScore, sub: '贝叶斯加权（0~5）', icon: 'Star', color: '#67c23a' },
    { label: '最高热度门店', value: hottest ? hottest.heat_index.toFixed(1) : '-', sub: hottest ? hottest.entity_name : '暂无指标数据', icon: 'TrendCharts', color: '#e6a23c' },
    { label: '笔记样本 / 总点赞', value: `${d.xhs_notes.length} / ${totalLikes}`, sub: '小红书 Top 100', icon: 'Notebook', color: '#9b59b6' },
  ]
})

const quadrantOption = computed(() => buildQuadrantOption(data.value?.indicators || []))
const scoreOption = computed(() => buildScoreOption(data.value?.dp_shops || []))
const womOption = computed(() => buildWomOption(data.value?.indicators || []))
const heatOption = computed(() => buildHeatOption(data.value?.indicators || []))
const sovOption = computed(() => buildSovOption(data.value?.indicators || []))
const xhsOption = computed(() => buildXhsOption(data.value?.xhs_notes || []))

function scrollToChart(id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<style scoped>
.kpi-row {
  margin-bottom: 4px;
}
.scope-card {
  margin-bottom: 16px;
}
.scope-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.scope-label {
  font-weight: 600;
}
.scope-select {
  width: min(320px, 100%);
  flex: 1 1 280px;
  max-width: 420px;
}
.scope-meta {
  color: #909399;
  font-size: 12px;
}
.kpi-card {
  margin-bottom: 16px;
}
.kpi-card :deep(.el-card__body) {
  padding: 16px 18px;
}
.kpi-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #909399;
  font-size: 13px;
}
.kpi-value {
  font-size: 26px;
  font-weight: 700;
  margin: 6px 0 2px;
}
.kpi-sub {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.anchor-card {
  scroll-margin-top: 70px;
  margin-bottom: 16px;
}
.section-title {
  margin-top: 8px;
}
.el-card {
  margin-bottom: 0;
}
.kpi-row + .section-title {
  margin-top: 8px;
}
.el-row .el-card {
  margin-bottom: 16px;
}

@media (max-width: 767px) {
  .scope-select {
    width: 100%;
    max-width: none;
  }

  .kpi-value {
    font-size: 22px;
  }

  .scope-meta {
    width: 100%;
  }
}
</style>
