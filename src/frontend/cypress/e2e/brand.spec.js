/**
 * e2e：登录 -> 打开 /brands -> 搜索 -> 点击进入详情。
 * 前置：FastAPI 与数据库已启动；npm run dev 通过 Vite proxy 访问后端。
 */
describe('品牌浏览路径', () => {
  it('登录 -> 品牌列表 -> 搜索 -> 进入详情', () => {
    // 1. 登录
    cy.visit('/#/login')
    cy.get('input[aria-label="用户名"]').type('admin')
    cy.get('input[aria-label="密码"]').type('123456')
    cy.get('button[aria-label="登录"]').click()
    cy.hash().should('eq', '#/')

    // 2. 打开品牌列表（来自真实 brands 主数据）
    cy.visit('/#/brands')
    cy.get('.el-table__row', { timeout: 10000 }).should('have.length.at.least', 1)

    // 3. 搜索「瑞幸」
    cy.get('input[aria-label="搜索品牌名"]').type('瑞幸{enter}')
    cy.get('.el-table__row').should('have.length', 1)

    // 4. 点击进入详情
    cy.get('.el-table__row').first().click()
    cy.hash().should('match', /#\/brands\/LK001/)
    cy.contains('热度指数趋势', { timeout: 10000 })
    cy.contains('最近采集')
  })
})
