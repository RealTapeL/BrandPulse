<template>
  <div class="bp-page-header">
    <div class="bp-page-header__copy">
      <div v-if="eyebrow" class="bp-page-header__eyebrow">{{ eyebrow }}</div>
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="bp-page-header__actions"><slot name="actions" /></div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
})
</script>

<style scoped>
.bp-page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.bp-page-header__copy { min-width: 0; }
.bp-page-header__eyebrow { margin-bottom: 6px; color: var(--bp-primary); font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1 { margin: 0; color: var(--bp-text-strong); font-size: 24px; line-height: 1.3; letter-spacing: -.01em; }
p { margin: 7px 0 0; color: var(--bp-text-muted); font-size: 13px; line-height: 1.6; }
.bp-page-header__actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 8px; flex: 0 0 auto; }
@media (max-width: 767px) { .bp-page-header { flex-direction: column; gap: 12px; } .bp-page-header__actions { width: 100%; justify-content: flex-start; } h1 { font-size: 21px; } }
</style>
