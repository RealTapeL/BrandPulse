# BrandPulse 前端开发说明

管理台原型（演示级）。技术栈：Vue 3 + Vite + Element Plus + ECharts + Pinia + axios，JavaScript（非 TS）。

## 环境要求

- Node.js >= 18（本机位于 `~/.local/node/bin`，不在默认 PATH 时先 `export PATH="$HOME/.local/node/bin:$PATH"`）

## 脚本

```bash
npm install          # 安装依赖
npm run dev          # 开发服务器（默认挂 mock，见下）
npm run build        # 构建到 dist/（生产由 FastAPI 静态托管）
npm run test:unit    # Vitest 单元测试（tests/unit/**/*.spec.js）
npm run storybook    # Storybook 组件演示（http://localhost:6006）
npm run cypress      # e2e（需先 npm run dev；headless 需系统装 Xvfb）
npm run cypress:open # Cypress 交互界面
```

注意：本机 shell 里有 `ELECTRON_RUN_AS_NODE=1`（vscode-server 注入），会让 Cypress 的 Electron 以 Node 模式启动失败，cypress 脚本已内置 `env -u` 处理；手动执行 `npx cypress` 时也要加 `env -u ELECTRON_RUN_AS_NODE`。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VITE_USE_MOCK` | dev 下默认开启 | `false` 时关闭 mock，走真实后端（vite proxy `/api` → `127.0.0.1:8000`） |

在 `.env.development` 中设置，例如后端就绪后：

```
VITE_USE_MOCK=false
```

## Mock 策略

- `src/mocks/index.js` 用 axios-mock-adapter 拦截 axios 实例（`src/api/index.js`，baseURL `/api/v1`），数据来自 `src/mocks/*.json`。
- 仅在 `import.meta.env.DEV && VITE_USE_MOCK !== 'false'` 时由 `src/main.js` 挂载，生产构建不含 mock。
- 未覆盖的接口返回 404 `{ message: 'mock 未覆盖该接口' }`，便于发现待补契约。
- 演示登录：任意非空用户名/密码均可登录，返回 `mock-jwt-token-for-demo`。

## 目录约定

```
src/api/        axios 封装与接口函数（index.js 为 configuredAxios）
src/stores/     Pinia stores（user / brands / agent）
src/mocks/      mock 数据与 axios-mock-adapter 挂载
src/views/      页面（Login / Dashboard / BrandList / BrandDetail / AgentConsole ...）
tests/unit/     Vitest 单元测试
```

## 后端 API 契约（/api/v1）

- `POST /auth/login` → `{ token, user: { id, username, role } }`
- `GET /brands?q=&category=&city=&page=&per_page=` → `{ items: Brand[], total }`
- `GET /brands/{id}` → `{ brand, stats: { indicators: [{date,value}] }, recent_crawls: [] }`
- `POST /brands/{id}/crawl` → `{ job_id }`
- `GET /indicators?brand_id=&start=&end=&indicator=` → `{ series: [{date,value}], meta }`
- `POST /agent/execute` → `{ task_id }`
- `GET /agent/tasks/{id}` → `{ id, status, input, output, logs }`

鉴权：axios 自动注入 `Authorization: Bearer <localStorage.token>`；401 统一清除 token 并跳转 `/login`。

## 两套 HTTP 封装说明（过渡期）

- 旧四页面（看板/对话/数据表/公式）用 `src/api/http.js`（fetch，对接现有 FastAPI `/api/*`），保持不变。
- 新管理台页面统一走 `src/api/index.js`（axios，`/api/v1/*` 契约）。后端就绪后逐步迁移旧页面。

## 实施路线

- 阶段 1（已完成）：axios 封装 + user store + Login + 路由守卫 + mock 登录 + vitest
- 阶段 2（已完成）：BrandList / BrandDetail / BrandTable + 分页 + Storybook
- 阶段 3（已完成）：Agent Console + agent store + Cypress e2e（登录→列表→搜索→详情）
