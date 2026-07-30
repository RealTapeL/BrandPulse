<template>
  <div class="brand-list-page">
    <!-- 搜索栏 -->
    <div class="filter-bar">
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
      @add="onAdd"
    />
  </div>
</template>

<script setup>
/**
 * 品牌列表页 /brands：搜索（q/品类/城市）+ 分页表格。
 * TODO: 「添加品牌」入口待后端提供品牌管理接口后接入。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import BrandTable from '../components/BrandTable.vue'
import { useBrandsStore } from '../stores/brands'

const router = useRouter()
const store = useBrandsStore()

// TODO: 品类/城市选项后续由后端字典接口下发
const categories = ['咖啡', '茶饮']
const cities = ['苏州']

onMounted(() => load())

function load(page = 1) {
  store.fetchList({ page })
}

function onSearch() {
  load(1)
}

function goDetail(row) {
  router.push(`/brands/${row.id}`)
}

function onAdd() {
  ElMessage.info('品牌管理功能待后端接口就绪后开放')
}
</script>

<style scoped>
.brand-list-page {
  padding: 20px;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.filter-q {
  width: 260px;
}
.filter-select {
  width: 130px;
}
.error-bar {
  margin-bottom: 12px;
}
</style>
