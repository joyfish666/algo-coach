#!/usr/bin/env node
/**
 * Static guard for i18n catalog integrity.
 *
 * The t() helper falls back silently to the raw key when a catalog entry is
 * missing, which once shipped a literal "cookie_invalid" into the UI. This
 * script makes that class of bug a CI failure instead:
 *   1. every key used via t('...') in source must exist in BOTH catalogs
 *   2. the zh and en catalogs must define identical key sets
 * Dynamic keys (template literals) are out of scope by design.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const srcDir = join(root, 'src')

function walk(dir, files = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      walk(full, files)
    } else if (/\.(vue|js)$/.test(name) && !name.endsWith('.test.js')) {
      files.push(full)
    }
  }
  return files
}

// catalog keys live at exactly one indent level inside `zh: {` / `en: {`
function extractCatalogKeys(source, locale) {
  const keys = new Set()
  const blockMatch = source.match(new RegExp(`${locale}: \\{([\\s\\S]*?)\\n  \\},`))
  if (!blockMatch) return keys
  for (const match of blockMatch[1].matchAll(/^    ([a-zA-Z0-9_]+):/gm)) {
    keys.add(match[1])
  }
  return keys
}

const files = walk(srcDir)
const usedByFile = new Map()
const USE_RE = /\bt\(\s*'([a-zA-Z0-9_]+)'/g

for (const file of files) {
  const source = readFileSync(file, 'utf8')
  const relative = file.slice(root.length + 1)
  if (relative.endsWith('stores\\i18n.js') || relative.endsWith('stores/i18n.js')) continue
  const used = [...source.matchAll(USE_RE)].map((m) => m[1])
  if (used.length) usedByFile.set(relative, used)
}

const i18nSource = readFileSync(join(srcDir, 'stores', 'i18n.js'), 'utf8')
const zhKeys = extractCatalogKeys(i18nSource, 'zh')
const enKeys = extractCatalogKeys(i18nSource, 'en')

// The block regex depends on the catalog's exact closing shape; a refactor
// could silently extract zero keys, pass the parity loop vacuously, and
// report every t() usage as missing instead of admitting the parse failed.
if (zhKeys.size === 0 || enKeys.size === 0) {
  console.error(
    `catalog extraction found 0 keys (zh=${zhKeys.size}, en=${enKeys.size}) - ` +
      'the catalog shape no longer matches the extraction regex; fix the regex'
  )
  process.exit(1)
}

let failed = false

for (const key of zhKeys) {
  if (!enKeys.has(key)) {
    console.error(`en catalog missing key: ${key}`)
    failed = true
  }
}
for (const key of enKeys) {
  if (!zhKeys.has(key)) {
    console.error(`zh catalog missing key: ${key}`)
    failed = true
  }
}

for (const [file, used] of usedByFile) {
  for (const key of used) {
    if (!zhKeys.has(key)) {
      console.error(`${file}: t('${key}') has no catalog entry`)
      failed = true
    }
  }
}

if (failed) process.exit(1)
console.log(
  `i18n ok: ${zhKeys.size} keys, ${usedByFile.size} files scanned, all usages covered in both locales`
)
