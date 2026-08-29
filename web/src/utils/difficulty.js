import { useI18nStore } from '../stores/i18n'

const LEVELS = ['easy', 'medium', 'hard']

/**
 * Shared difficulty presentation, mirroring the utils/verdict.js precedent:
 * one mapping so chips/labels cannot drift between the list, the workbench,
 * analytics and the daily card.
 */
export function difficultyKey(value) {
  const level = (value || '').toLowerCase()
  return LEVELS.includes(level) ? `diff_${level}` : null
}

/**
 * Localized label; pass fallback={value} where the raw enum is the useful
 * fallback (workbench header, recommendations) and '' where an empty chip
 * is (cards).
 */
export function difficultyLabel(value, fallback = '') {
  const key = difficultyKey(value)
  return key ? useI18nStore().t(key) : fallback
}

// semantic color class comes straight from the token palette so the chip
// can never drift from the rest of the design system
export function difficultyClass(value) {
  const level = (value || '').toLowerCase()
  return LEVELS.includes(level) ? `chip-${level}` : ''
}
