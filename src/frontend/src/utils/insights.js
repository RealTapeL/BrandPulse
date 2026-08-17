const numeric = (value) => Number.isFinite(Number(value)) ? Number(value) : null

export function average(rows, field) {
  const values = rows.map((row) => numeric(row[field])).filter((value) => value !== null)
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

export function formatNumber(value, digits = 0) {
  const parsed = numeric(value)
  if (parsed === null) return '-'
  return parsed.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

export function formatPercent(value, digits = 1) {
  const parsed = numeric(value)
  return parsed === null ? '-' : `${(parsed * 100).toFixed(digits)}%`
}

export function sourceFreshness(value, staleAfterHours = 72) {
  if (!value) return { state: 'missing', label: '数据未就绪', timestamp: null }
  const raw = String(value)
  const timestamp = new Date(raw.includes('T') ? raw : `${raw}T00:00:00`).getTime()
  if (Number.isNaN(timestamp)) return { state: 'missing', label: '数据未就绪', timestamp: null }
  const ageHours = (Date.now() - timestamp) / 36e5
  if (ageHours > staleAfterHours) return { state: 'stale', label: '数据已过期', timestamp }
  return { state: 'fresh', label: '数据可用', timestamp }
}

/**
 * 仅从本次真实快照的相对位置推导机会，不把横截面比较伪装成趋势预测。
 */
export function deriveOpportunities(indicators = []) {
  const scoreAverage = average(indicators, 'weighted_score')
  const sovAverage = average(indicators, 'sov')
  if (scoreAverage === null || sovAverage === null) return []

  const opportunities = []
  for (const item of indicators) {
    const score = numeric(item.weighted_score)
    const sov = numeric(item.sov)
    if (score === null || sov === null) continue
    const unconfirmed = item.entity_mapping_status !== 'confirmed'
    const entity = item.entity_name || '未命名公开门店'
    if (score >= scoreAverage && sov < sovAverage) {
      opportunities.push({
        key: `potential-${entity}`,
        entity,
        type: '机会',
        rule: unconfirmed ? '高口碑 · 低点评评价份额（待映射）' : '高口碑 · 低点评评价份额',
        detail: `贝叶斯口碑 ${formatNumber(score, 2)} 高于当前范围均值，点评评价份额 ${formatPercent(sov)} 低于均值。${unconfirmed ? '该公开门店尚未确认到品牌/门店主数据，只能作为待核实线索。' : ''}`,
        action: unconfirmed ? '处理门店映射' : '查看竞争观测',
        actionPath: unconfirmed ? '/data?tab=matching' : '/brands',
        priority: Math.max(0, score - scoreAverage) + Math.max(0, sovAverage - sov),
      })
    }
    const momentum = numeric(item.wow_momentum)
    if (momentum !== null && momentum > 0) {
      opportunities.push({
        key: `momentum-${item.entity_name}`,
        entity: item.entity_name,
        type: '信号',
        rule: '已有正向周环比动量',
        detail: `当前指标记录的周环比动量为 ${(momentum * 100).toFixed(1)}%，需结合后续快照继续验证。`,
        action: '查看指标详情',
        priority: momentum,
      })
    }
  }
  return opportunities.sort((a, b) => b.priority - a.priority)
}

export function buildFocusItems({ data, governance } = {}) {
  const items = []
  const indicators = data?.indicators || []
  deriveOpportunities(indicators).slice(0, 2).forEach((item) => items.push({ ...item, actionPath: '/opportunities' }))

  const openIssues = Number(governance?.records?.open_issues || 0)
  if (openIssues > 0) {
    items.push({ key: 'governance', type: '数据问题', rule: '数据质量待处理', entity: `${openIssues} 个治理问题`, detail: `当前有 ${openIssues} 个开放的数据质量问题，可能影响品牌判断和汇总口径。`, action: '处理数据问题', actionPath: '/data?tab=quality', priority: 1000 + openIssues })
  }
  const xhsLatest = (data?.xhs_notes || []).reduce((latest, note) => (note.crawl_date || '') > latest ? note.crawl_date : latest, '')
  const xhsFreshness = sourceFreshness(xhsLatest)
  if (xhsFreshness.state !== 'fresh') {
    items.push({ key: 'xhs-freshness', type: '数据问题', rule: '小红书来源状态', entity: '小红书数据', detail: xhsFreshness.state === 'stale' ? '小红书数据超过 72 小时未更新，内容洞察不应作为即时判断依据。' : '当前范围没有可用的小红书采集记录。', action: '查看采集计划', actionPath: '/automation?tab=collection', priority: 900 })
  }
  if (!indicators.length) {
    items.push({ key: 'missing-indicators', type: '数据问题', rule: '指标未就绪', entity: '品牌竞争指标', detail: '当前范围尚无可用于竞争分析的指标日表，暂不能生成机会判断。', action: '查看数据中心', actionPath: '/data?tab=overview', priority: 1100 })
  }
  return items.sort((a, b) => b.priority - a.priority).slice(0, 5)
}
