import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(ElementPlus, { locale: zhCn })
app.use(router)

async function bootstrap() {
  // 开发环境默认挂 mock（axios-mock-adapter 拦截 /api/v1/*）；
  // 后端就绪后在 .env.development 设 VITE_USE_MOCK=false 即可走真实接口。
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK !== 'false') {
    const [{ setupMock }, { default: api }] = await Promise.all([
      import('./mocks'),
      import('./api'),
    ])
    setupMock(api)
  }
  app.mount('#app')
}

bootstrap()
