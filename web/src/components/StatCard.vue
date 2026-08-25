<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: String, default: '--' },
})
</script>

<template>
  <div class="card stat-card">
    <div class="eyebrow">{{ label }}</div>
    <div class="stat-value">{{ value }}</div>
  </div>
</template>

<style scoped>
.stat-card {
  padding: var(--space-7);
}

.stat-value {
  font-size: var(--font-size-page);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  margin-top: var(--space-2);
}
</style>
