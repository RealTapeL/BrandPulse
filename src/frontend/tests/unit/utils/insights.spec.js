import { buildFocusItems, deriveOpportunities, sourceFreshness } from '../../../src/utils/insights'

describe('insight rules', () => {
  const indicators = [
    { entity_name: '高口碑低份额', weighted_score: 4.8, sov: 0.1, entity_mapping_status: 'pending' },
    { entity_name: '低口碑高份额', weighted_score: 3.1, sov: 0.5, entity_mapping_status: 'confirmed' },
    { entity_name: '基准门店', weighted_score: 4.0, sov: 0.4, entity_mapping_status: 'confirmed' },
  ]

  it('只根据当前快照的口碑和点评评价份额生成待核实线索，不伪造热度或变化率', () => {
    const items = deriveOpportunities(indicators)
    expect(items.some((item) => item.entity === '高口碑低份额' && item.rule.includes('高口碑 · 低点评评价份额'))).toBe(true)
    expect(items.some((item) => item.actionPath === '/data?tab=matching')).toBe(true)
    expect(items.some((item) => item.rule.includes('高热度'))).toBe(false)
    expect(items.some((item) => item.rule.includes('动量'))).toBe(false)
  })

  it('数据质量问题优先进入今日关注', () => {
    const items = buildFocusItems({ data: { indicators, xhs_notes: [] }, governance: { records: { open_issues: 2 } } })
    expect(items[0]).toMatchObject({ type: '数据问题', entity: '2 个治理问题' })
  })

  it('缺失或过期来源会明确标记为不可用于即时判断', () => {
    expect(sourceFreshness('').state).toBe('missing')
    expect(sourceFreshness('2020-01-01').state).toBe('stale')
  })
})
