<template>
  <div class="brand-table" v-loading="loading">
    <!-- 桌面端：表格（>=1024px） -->
    <el-table
      v-if="!isCompact"
      :data="rows"
      aria-label="品牌列表表格"
      @row-click="(row) => $emit('row-click', row)"
    >
      <el-table-column label="品牌" min-width="240">
        <template #default="{ row }">
          <div class="brand-cell">
            <el-avatar :size="32" :src="row.logo_url || undefined" class="brand-logo">
              {{ row.name.slice(0, 1) }}
            </el-avatar>
            <span class="brand-name">{{ row.name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="品类" width="100" />
      <el-table-column prop="city" label="城市" width="90" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近采集" width="180">
        <template #default="{ row }">{{ formatTime(row.last_crawl_at) }}</template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无品牌数据">
          <el-button type="primary" aria-label="添加品牌" @click="$emit('add')">添加品牌</el-button>
        </el-empty>
      </template>
    </el-table>

    <!-- 小屏：卡片列表（<1024px） -->
    <div v-else class="card-list">
      <template v-if="rows.length">
        <el-card
          v-for="row in rows"
          :key="row.id"
          class="brand-card"
          shadow="hover"
          @click="$emit('row-click', row)"
        >
          <div class="card-head">
            <el-avatar :size="36" :src="row.logo_url || undefined">{{ row.name.slice(0, 1) }}</el-avatar>
            <div class="card-title">
              <div class="brand-name">{{ row.name }}</div>
              <div class="card-sub">{{ row.category }} · {{ row.city }}</div>
            </div>
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </div>
          <div class="card-foot">最近采集：{{ formatTime(row.last_crawl_at) }}</div>
        </el-card>
      </template>
      <el-empty v-else description="暂无品牌数据">
        <el-button type="primary" aria-label="添加品牌" @click="$emit('add')">添加品牌</el-button>
      </el-empty>
    </div>

    <div class="pager">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="total"
        :page-size="perPage"
        :current-page="page"
        aria-label="品牌列表分页"
        @current-change="(p) => $emit('page-change', p)"
      />
    </div>
  </div>
</template>

<script setup>
/**
 * BrandTable：品牌列表展示组件（桌面表格 / <1024px 卡片列表 + 分页）。
 * 纯展示组件，数据通过 props 传入，便于 Storybook 演示与单测。
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'

defineProps({
  rows: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  perPage: { type: Number, default: 10 },
  loading: { type: Boolean, default: false },
})

defineEmits(['page-change', 'row-click', 'add'])

const isCompact = ref(false)
const mq = window.matchMedia('(max-width: 1023px)')
const sync = () => (isCompact.value = mq.matches)

onMounted(() => {
  sync()
  mq.addEventListener('change', sync)
})
onBeforeUnmount(() => mq.removeEventListener('change', sync))

function statusType(s) {
  return { active: 'success', crawling: 'warning', error: 'danger' }[s] || 'info'
}

function statusText(s) {
  return { active: '正常', crawling: '采集中', error: '异常' }[s] || s
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}
</script>

<style scoped>
.brand-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-logo {
  flex-shrink: 0;
  background: #ecf5ff;
  color: #409eff;
}
.brand-name {
  font-weight: 500;
}
:deep(.el-table__row) {
  cursor: pointer;
}
.card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.brand-card {
  cursor: pointer;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.card-title {
  flex: 1;
  min-width: 0;
}
.card-sub {
  color: #909399;
  font-size: 12px;
  margin-top: 2px;
}
.card-foot {
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
