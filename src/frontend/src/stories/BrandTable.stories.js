/**
 * BrandTable 组件故事：默认（含数据）/ 加载态 / 空态。
 * 演示数据来自 src/mocks/brands.json，与开发 mock 保持一致。
 */
import BrandTable from '../components/BrandTable.vue'
import brandsData from '../mocks/brands.json'

export default {
  title: 'Components/BrandTable',
  component: BrandTable,
  argTypes: {
    'onPage-change': { action: 'page-change' },
    'onRow-click': { action: 'row-click' },
    onAdd: { action: 'add' },
  },
}

const Template = (args) => ({
  components: { BrandTable },
  setup: () => ({ args }),
  template:
    '<BrandTable v-bind="args" @page-change="args[\'onPage-change\']" @row-click="args[\'onRow-click\']" @add="args.onAdd" />',
})

export const Default = Template.bind({})
Default.args = {
  rows: brandsData.items.slice(0, 10),
  total: brandsData.total,
  page: 1,
  perPage: 10,
  loading: false,
}

export const Loading = Template.bind({})
Loading.args = { ...Default.args, rows: [], loading: true }

export const Empty = Template.bind({})
Empty.args = { ...Default.args, rows: [], total: 0 }
