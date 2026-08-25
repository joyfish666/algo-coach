// One shared mapping from a verdict status_key to its i18n label and semantic
// tone. History and the judge result panel used to implement this separately
// and drift: History rendered raw English enums while the panel translated
// the same values.
const FAILED_KEYS = [
  'wrong_answer',
  'runtime_error',
  'compile_error',
  'tle',
  'mle',
  'ole',
  'internal_error',
]

export function verdictTone(statusKey) {
  if (statusKey === 'accepted') return 'accepted'
  if (FAILED_KEYS.includes(statusKey)) return 'failed'
  return 'unknown'
}

export function verdictLabel(i18n, statusKey, fallback = '') {
  const translated = i18n.t(`verdict_${statusKey}`)
  // an untranslated key echoes itself -> fall back to the caller's text
  return translated !== `verdict_${statusKey}` ? translated : fallback
}
