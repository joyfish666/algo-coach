<script setup>
// Five-pointed star for the favorite toggle. A text glyph (★/☆) renders
// differently per platform font; the SVG keeps one shape everywhere, and
// `1em` sizing follows the host button's font-size.
defineProps({
  filled: { type: Boolean, default: false },
})
</script>

<template>
  <svg
    class="star-icon"
    viewBox="0 0 24 24"
    width="1em"
    height="1em"
    aria-hidden="true"
    focusable="false"
  >
    <path
      d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"
      :fill="filled ? 'currentColor' : 'none'"
      stroke="currentColor"
      stroke-width="2"
      stroke-linejoin="round"
    />
  </svg>
</template>

<style scoped>
.star-icon {
  display: block;
}
</style>
