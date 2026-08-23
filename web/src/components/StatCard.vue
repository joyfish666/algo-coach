<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: String, default: '--' },
})
</script>

<template>
  <div class="card stat-card">
    <div class="stat-value">{{ value }}</div>
    <div class="stat-label">{{ label }}</div>
  </div>
</template>

<style scoped>
.stat-card {
  padding: var(--space-6);
  text-align: center;
}

.stat-value {
  font-size: var(--font-size-page);
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin-top: var(--space-1);
}
</style>
