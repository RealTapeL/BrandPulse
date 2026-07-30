<template>
  <div ref="el" class="echart" :style="{ height }" v-loading="loading"></div>
</template>

<script setup>
/**
 * ECharts 通用容器组件：负责 init / option 更新 / resize / dispose。
 * 图表 option 的构造逻辑见 src/components/dashboard/chartOptions.js
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '360px' },
  loading: { type: Boolean, default: false },
})

const el = ref(null)
let chart = null

const onResize = () => chart && chart.resize()

onMounted(() => {
  chart = echarts.init(el.value)
  chart.setOption(props.option)
  window.addEventListener('resize', onResize)
})

watch(
  () => props.option,
  (opt) => {
    if (chart && opt) chart.setOption(opt, true)
  },
  { deep: true }
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.echart {
  width: 100%;
}
</style>
