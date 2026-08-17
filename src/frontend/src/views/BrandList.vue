<template>
  <div class="page brand-list-page">
    <PageHeader title="品牌库" description="按品牌、品类和城市筛选已登记的真实品牌主数据；指标与趋势需进入详情页查看。">
      <template #actions><el-button plain @click="router.push('/watchlist')"><el-icon><Star /></el-icon>关注清单</el-button></template>
    </PageHeader>

    <!-- 搜索栏 -->
    <div class="filter-bar toolbar">
      <el-input
        v-model="store.query.q"
        class="filter-q"
        placeholder="搜索品牌名"
        clearable
        aria-label="搜索品牌名"
        @keyup.enter="onSearch"
        @clear="onSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select
        v-model="store.query.category"
        placeholder="品类"
        clearable
        aria-label="按品类筛选"
        class="filter-select"
        @change="onSearch"
      >
        <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
      </el-select>
      <el-select
        v-model="store.query.city"
        placeholder="城市"
        clearable
        aria-label="按城市筛选"
        class="filter-select"
        @change="onSearch"
      >
        <el-option v-for="c in cities" :key="c" :label="c" :value="c" />
      </el-select>
      <el-button type="primary" aria-label="查询品牌" @click="onSearch">查询</el-button>
    </div>

    <!-- 错误态：retry -->
    <el-alert
      v-if="store.error"
      type="error"
      title="品牌列表加载失败"
      :closable="false"
      class="error-bar"
    >
      <el-button size="small" aria-label="重试加载品牌列表" @click="load()">重试</el-button>
    </el-alert>

    <BrandTable
      :rows="store.items"
      :total="store.total"
      :page="store.page"
      :per-page="store.perPage"
      :loading="store.loading"
      @page-change="load"
      @row-click="goDetail"
    />
  </div>
</template>

<script setup>
/**
 * 品牌列表页 /brands：搜索（q/品类/城市）+ 分页表格。
 * 筛选项由后端主数据下发，避免前端把业务品类和城市写死。
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import BrandTable from '../components/BrandTable.vue'
import PageHeader from '../components/PageHeader.vue'
import { useBrandsStore } from '../stores/brands'

const router = useRouter()
const store = useBrandsStore()

const categories = computed(() => store.filters.categories)
const cities = computed(() => store.filters.cities)

onMounted(() => {
  store.fetchFilters().catch(() => {})
  load()
})

function load(page = 1) {
  store.fetchList({ page })
}

function onSearch() {
  load(1)
}

function goDetail(row) {
  router.push(`/brands/${row.id}`)
}

</script>

<style scoped>
.brand-list-page {
  min-width: 0;
}
.filter-bar {
  align-items: center;
  padding: 14px;
  border: 1px solid var(--bp-card-border);
  border-radius: var(--bp-radius-md);
  background: var(--bp-surface);
  box-shadow: var(--bp-shadow-card);
}
.filter-q {
  width: min(360px, 100%);
  flex: 1 1 240px;
}
.filter-select {
  width: 150px;
  flex: 0 1 150px;
}
.error-bar {
  margin-bottom: 12px;
}

@media (max-width: 767px) {
  .filter-q,
  .filter-select {
    width: 100%;
    flex-basis: 100%;
  }
}
</style>
