// Cypress 配置：e2e 跑在 vite dev server（5173）上，hash 路由
import { defineConfig } from 'cypress'

export default defineConfig({
  e2e: {
    baseUrl: 'http://localhost:5173',
    specPattern: 'cypress/e2e/**/*.spec.js',
    supportFile: false,
    video: false,
    // 桌面表格布局需要 >=1024px 视口（<1024px 时 BrandTable 切换为卡片列表）
    viewportWidth: 1280,
    viewportHeight: 800,
  },
})
