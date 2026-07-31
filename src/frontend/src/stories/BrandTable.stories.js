/**
 * BrandTable 组件故事：默认（含数据）/ 加载态 / 空态。
 * Storybook 使用独立静态样例，不依赖应用运行时数据。
 */
import BrandTable from '../components/BrandTable.vue'

const rows = [
  { id: 'LK001', name: '瑞幸咖啡', logo_url: '', category: '咖啡', city: '苏州', status: 'active', last_crawl_at: '2026-07-29T10:16:04.252Z' },
  { id: 'SB001', name: '星巴克', logo_url: '', category: '咖啡', city: '上海', status: 'crawling', last_crawl_at: '2026-07-28T10:16:04.252Z' },
]

export default {
  title: 'Components/BrandTable',
  component: BrandTable,
  argTypes: {
    'onPage-change': { action: 'page-change' },
    'onRow-click': { action: 'row-click' },
  },
}

const Template = (args) => ({
  components: { BrandTable },
  setup: () => ({ args }),
  template:
    '<BrandTable v-bind="args" @page-change="args[\'onPage-change\']" @row-click="args[\'onRow-click\']" />',
})

export const Default = Template.bind({})
Default.args = {
  rows,
  total: rows.length,
  page: 1,
  perPage: 10,
  loading: false,
}

export const Loading = Template.bind({})
Loading.args = { ...Default.args, rows: [], loading: true }

export const Empty = Template.bind({})
Empty.args = { ...Default.args, rows: [], total: 0 }
