# BrandPulse 前端开发说明

管理台。技术栈：Vue 3 + Vite + Element Plus + ECharts + Pinia + axios，JavaScript（非 TS）。所有页面调用真实 FastAPI，不使用运行时 Mock 数据。

## 环境要求

- Node.js >= 18（本机位于 `~/.local/node/bin`，不在默认 PATH 时先 `export PATH="$HOME/.local/node/bin:$PATH"`）

## 脚本

```bash
npm install          # 安装依赖
npm run dev          # 开发服务器（/api 代理至本机 FastAPI）
npm run build        # 构建到 dist/（生产由 FastAPI 静态托管）
npm run test:unit    # Vitest 单元测试（tests/unit/**/*.spec.js）
npm run storybook    # Storybook 组件演示（http://localhost:6006）
npm run cypress      # e2e（需先 npm run dev；headless 需系统装 Xvfb）
npm run cypress:open # Cypress 交互界面
```

注意：本机 shell 里有 `ELECTRON_RUN_AS_NODE=1`（vscode-server 注入），会让 Cypress 的 Electron 以 Node 模式启动失败，cypress 脚本已内置 `env -u` 处理；手动执行 `npx cypress` 时也要加 `env -u ELECTRON_RUN_AS_NODE`。

Cypress 不保存账号或密码。执行需要登录的 e2e 时，从安全环境变量提供测试账号，例如：

```bash
CYPRESS_USERNAME='<测试账号>' CYPRESS_PASSWORD='<测试密码>' npm run cypress
```

没有这两个变量时，登录路径用例会明确跳过。

## 后端依赖

开发与生产均调用真实 FastAPI。启动前请保证 PostgreSQL、Redis、RQ Worker 与后端服务可用。
Vite 会把 `/api` 代理到 `127.0.0.1:8000`；FastAPI 静态托管构建产物时则同源访问。

默认 `AUTH_MODE=local`，仅用于本机开发，可使用任意非空凭据登录。生产和共享环境使用
`AUTH_MODE=rbac`：运行 `.venv/bin/python scripts/configure_production_auth.py` 生成强签名密钥和初始管理员。
Access Token 仅存在浏览器内存；刷新页面由 HttpOnly 刷新 Cookie 恢复会话。

## 目录约定

```
src/api/        axios 封装与接口函数（index.js 为 configuredAxios）
src/stores/     Pinia stores（user / brands / agent）
src/views/      页面（Login / Dashboard / BrandList / BrandDetail / AgentConsole ...）
tests/unit/     Vitest 单元测试
```

## 后端 API 契约（/api/v1）

- `POST /auth/login` → `{ token, user: { id, username, role, permissions } }`
- `POST /auth/refresh`、`POST /auth/logout`、`POST /auth/change-password`
- `GET|POST|PUT /users` → 管理员账号、角色和一次性临时密码管理
- `GET /brands?q=&category=&city=&page=&per_page=` → `{ items: Brand[], total }`
- `GET /brands/filters` → `{ categories, cities }`
- `GET /brands/{id}` → `{ brand, stats: { indicators: [{date,value}] }, recent_crawls: [] }`
- `POST /brands/{id}/crawl` → `{ job_id }`
- `GET /indicators?brand_id=&start=&end=&indicator=` → `{ series: [{date,value}], meta }`
- `POST /agent/execute` → `{ task_id, rq_job_id, status }`
- `GET /agent/tasks` / `GET /agent/tasks/{id}` → 持久化任务历史与 `{ id, status, input, output, logs }`
- `GET /dashboard`、`GET /tables/{table_name}`、`POST /chat`
- `GET|POST|PUT|DELETE /formulas`

鉴权：axios 自动注入内存中的 `Authorization: Bearer <token>`；401 统一清除会话并跳转 `/login`。

所有页面统一使用 `src/api/index.js` 中的 axios 实例；它自动注入浏览器会话 token 并处理服务端错误。

## 实施路线

- 品牌、Agent、聊天、数据表与公式管理均已接入真实后端。
