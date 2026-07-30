/**
 * 看板图表 option 构造（浅色主题）。
 * 从原单页 App.vue 迁移，逻辑保持不变，配色适配亮色卡片背景。
 */

const AXIS_LABEL = { color: '#606266' }
const AXIS_LINE = { lineStyle: { color: '#dcdfe6' } }
const SPLIT_LINE = { lineStyle: { color: '#ebeef5' } }

export const shortName = (s) => (s && s.length > 12 ? s.slice(0, 12) + '…' : s)

const categoryAxis = (names) => ({
  type: 'category',
  data: names,
  axisLabel: { ...AXIS_LABEL, rotate: 30, formatter: shortName },
  axisLine: AXIS_LINE,
})

const valueAxis = () => ({
  type: 'value',
  axisLabel: AXIS_LABEL,
  axisLine: { show: false },
  splitLine: SPLIT_LINE,
})

function barOption(names, series) {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 10, right: 20, top: 30, bottom: 60, containLabel: true },
    xAxis: categoryAxis(names),
    yAxis: valueAxis(),
    series,
  }
}

/** 四象限气泡图：X=口碑分 Y=热度 气泡=SOV，分割线取均值 */
export function buildQuadrantOption(ind) {
  const avgScore = ind.reduce((s, r) => s + r.weighted_score, 0) / (ind.length || 1)
  const avgHeat = ind.reduce((s, r) => s + r.heat_index, 0) / (ind.length || 1)
  const maxSov = Math.max(...ind.map((r) => r.sov || 0), 0.01)
  return {
    tooltip: {
      formatter: (p) =>
        `${p.data[3]}<br/>口碑分：${p.data[0]}　热度：${p.data[1]}<br/>SOV：${(p.data[2] * 100).toFixed(1)}%`,
    },
    grid: { left: 20, right: 40, top: 30, bottom: 40, containLabel: true },
    xAxis: { type: 'value', name: '口碑分', axisLabel: AXIS_LABEL, axisLine: AXIS_LINE, splitLine: { show: false } },
    yAxis: { type: 'value', name: '热度指数', axisLabel: AXIS_LABEL, axisLine: AXIS_LINE, splitLine: { show: false } },
    series: [
      {
        type: 'scatter',
        data: ind.map((r) => [r.weighted_score, r.heat_index, r.sov || 0, r.entity_name]),
        symbolSize: (d) => 12 + 40 * Math.sqrt(d[2] / maxSov),
        itemStyle: { color: '#409eff', opacity: 0.75 },
        label: { show: true, position: 'top', color: '#606266', formatter: (p) => shortName(p.data[3]) },
        markLine: {
          silent: true,
          lineStyle: { color: '#909399', type: 'dashed' },
          label: { color: '#909399' },
          data: [{ xAxis: avgScore }, { yAxis: avgHeat }],
        },
      },
    ],
  }
}

/** 门店评分对比（评分 + 人均） */
export function buildScoreOption(shops) {
  return barOption(
    shops.map((s) => s.shop_name),
    [
      { name: '评分', type: 'bar', data: shops.map((s) => s.score), itemStyle: { color: '#409eff' } },
      { name: '人均(元)', type: 'bar', data: shops.map((s) => s.avg_price), itemStyle: { color: '#f778ba' } },
    ]
  )
}

/** 门店口碑分对比 */
export function buildWomOption(ind) {
  return barOption(
    ind.map((r) => r.entity_name),
    [{ name: '口碑分', type: 'bar', data: ind.map((r) => r.weighted_score), itemStyle: { color: '#67c23a' } }]
  )
}

/** 门店热度指数对比 */
export function buildHeatOption(ind) {
  return barOption(
    ind.map((r) => r.entity_name),
    [{ name: '热度指数', type: 'bar', data: ind.map((r) => r.heat_index), itemStyle: { color: '#e6a23c' } }]
  )
}

/** SOV 声量份额饼图 */
export function buildSovOption(ind) {
  return {
    tooltip: { formatter: (p) => `${p.name}<br/>SOV：${(p.value * 100).toFixed(1)}%` },
    series: [
      {
        type: 'pie',
        radius: ['35%', '70%'],
        data: ind.map((r) => ({ name: r.entity_name, value: r.sov || 0 })),
        label: { color: '#606266', formatter: (p) => `${shortName(p.name)} ${(p.value * 100).toFixed(0)}%` },
      },
    ],
  }
}

/** 小红书点赞 Top10（横向 bar） */
export function buildXhsOption(notes) {
  const top10 = notes.slice(0, 10).reverse()
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 10, right: 40, top: 10, bottom: 10, containLabel: true },
    xAxis: valueAxis(),
    yAxis: { type: 'category', data: top10.map((n) => shortName(n.title)), axisLabel: AXIS_LABEL, axisLine: AXIS_LINE },
    series: [
      {
        name: '点赞',
        type: 'bar',
        data: top10.map((n) => n.likes),
        itemStyle: { color: '#9b59b6' },
        label: { show: true, position: 'right', color: '#909399' },
      },
    ],
  }
}
