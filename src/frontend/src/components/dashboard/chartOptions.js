/**
 * 看板图表 option 构造（浅色主题）。
 * 只保留当前工作台使用、且有可信快照口径的图表。
 */

const AXIS_LABEL = { color: '#606266' }
const AXIS_LINE = { lineStyle: { color: '#dcdfe6' } }
const SPLIT_LINE = { lineStyle: { color: '#ebeef5' } }

export const shortName = (s) => (s && s.length > 12 ? s.slice(0, 12) + '…' : s)

const categoryAxis = (names) => ({
  type: 'category',
  data: names,
  axisLabel: { ...AXIS_LABEL, rotate: 30, hideOverlap: true, formatter: shortName },
  axisLine: AXIS_LINE,
})

const valueAxis = () => ({
  type: 'value',
  axisLabel: AXIS_LABEL,
  axisLine: { show: false },
  splitLine: SPLIT_LINE,
})

/**
 * 点评单源竞争观测：X=贝叶斯口碑，Y=点评评价份额，气泡=累计评价数。
 * 它不把累计公开评价伪装成近期热度，也不混入小红书缺失来源。
 */
export function buildReviewShareOption(indicators) {
  const rows = indicators.filter((row) => (
    Number.isFinite(Number(row.weighted_score))
    && Number.isFinite(Number(row.sov))
    && Number.isFinite(Number(row.review_count))
  ))
  const scores = rows.map((row) => Number(row.weighted_score))
  const shares = rows.map((row) => Number(row.sov))
  const reviews = rows.map((row) => Math.max(Number(row.review_count), 0))
  const avgScore = scores.reduce((sum, value) => sum + value, 0) / (scores.length || 1)
  const avgShare = shares.reduce((sum, value) => sum + value, 0) / (shares.length || 1)
  const maxReview = Math.max(...reviews, 1)
  const scorePadding = Math.max((Math.max(...scores, avgScore) - Math.min(...scores, avgScore)) * 0.14, 0.08)
  const sharePadding = Math.max((Math.max(...shares, avgShare) - Math.min(...shares, avgShare)) * 0.14, 0.01)
  const scoreMin = Math.min(...scores, avgScore) - scorePadding
  const scoreMax = Math.max(...scores, avgScore) + scorePadding
  const shareMin = Math.max(0, Math.min(...shares, avgShare) - sharePadding)
  const shareMax = Math.min(1, Math.max(...shares, avgShare) + sharePadding)
  const labelledNames = new Set(
    [...rows]
      .sort((left, right) => Number(right.review_count) - Number(left.review_count))
      .slice(0, 3)
      .map((item) => item.entity_name)
  )
  return {
    tooltip: {
      formatter: (point) => {
        const mapping = point.data[4] === 'confirmed' ? '已确认映射' : '待主数据确认'
        return `${point.data[3]}<br/>贝叶斯口碑：${Number(point.data[0]).toFixed(2)}<br/>点评评价份额：${(Number(point.data[1]) * 100).toFixed(1)}%<br/>点评累计评价：${Number(point.data[2]).toLocaleString('zh-CN')} 条<br/>映射状态：${mapping}`
      },
    },
    grid: { left: 28, right: 36, top: 30, bottom: 42, containLabel: true },
    xAxis: { type: 'value', name: '贝叶斯口碑（点评）', min: scoreMin, max: scoreMax, axisLabel: AXIS_LABEL, axisLine: AXIS_LINE, splitLine: { show: false } },
    yAxis: { type: 'value', name: '点评评价份额', min: shareMin, max: shareMax, axisLabel: { ...AXIS_LABEL, formatter: (value) => `${(value * 100).toFixed(0)}%` }, axisLine: AXIS_LINE, splitLine: { show: false } },
    series: [{
      type: 'scatter',
      data: rows.map((row) => [row.weighted_score, row.sov, row.review_count, row.entity_name, row.entity_mapping_status]),
      symbolSize: (value) => 12 + 36 * Math.sqrt(Math.max(value[2], 0) / maxReview),
      itemStyle: { color: '#409eff', opacity: 0.75 },
      label: {
        show: true,
        position: 'top',
        color: '#53667b',
        fontSize: 11,
        formatter: (point) => labelledNames.has(point.data[3]) ? shortName(point.data[3]) : '',
      },
      markLine: {
        silent: true,
        lineStyle: { color: '#909399', type: 'dashed' },
        label: { color: '#909399' },
        data: [{ xAxis: avgScore }, { yAxis: avgShare }],
      },
    }],
  }
}

/** 已计算的周环比动量排序。没有历史数据时由页面展示空态，不生成伪趋势。 */
export function buildMomentumOption(ind) {
  const rows = [...ind].sort((a, b) => (Number(b.wow_momentum) || 0) - (Number(a.wow_momentum) || 0))
  return {
    tooltip: { trigger: 'axis', formatter: (items) => `${items[0]?.name || ''}<br/>周环比动量：${((items[0]?.value || 0) * 100).toFixed(1)}%` },
    grid: { left: 18, right: 28, top: 20, bottom: 58, containLabel: true },
    xAxis: categoryAxis(rows.map((row) => row.entity_name)),
    yAxis: { ...valueAxis(), axisLabel: { ...AXIS_LABEL, formatter: (value) => `${(value * 100).toFixed(0)}%` } },
    series: [{ name: '周环比动量', type: 'bar', data: rows.map((row) => row.wow_momentum), itemStyle: { color: '#4b8ff0', borderRadius: [4, 4, 0, 0] } }],
  }
}
