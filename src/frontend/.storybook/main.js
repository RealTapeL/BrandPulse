/** Storybook 主配置：Vue3 + Vite builder，加载 src/stories 下的故事 */
export default {
  stories: ['../src/stories/**/*.stories.js'],
  addons: ['@storybook/addon-essentials'],
  framework: {
    name: '@storybook/vue3-vite',
    options: {},
  },
}
