/** Storybook 全局预览：注册 Element Plus 与图标、引入样式，保持与主应用一致 */
import { setup } from '@storybook/vue3'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import '../src/styles/main.css'

setup((app) => {
  app.use(ElementPlus, { locale: zhCn })
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }
})

export default {
  parameters: {
    controls: { expanded: true },
  },
}
