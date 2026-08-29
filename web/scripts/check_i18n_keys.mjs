#!/usr/bin/env node
/**
 * Static guard for i18n catalog integrity.
 *
 * The t() helper falls back silently to the raw key when a catalog entry is
 * missing, which once shipped a literal "cookie_invalid" into the UI. This
 * script makes that class of bug a CI failure instead:
 *   1. every key used via t('...') in source must exist in BOTH catalogs
 *   2. the zh and en catalogs must define identical key sets
 *   3. every catalog key must be REACHABLE: a key nothing can surface is dead
 *      copy that rots silently (setup_body kept claiming the setup wizard
 *      "arrives in a later release" long after the wizard shipped). Dynamic
 *      keys are out of reach of the literal scan by design, so reachability
 *      is accepted from four sources - see REACHABILITY below.
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
// 1. direct call sites: t('...')
const USE_RE = /\bt\(\s*'([a-zA-Z0-9_]+)'/g
// 2. object-literal props that views hand to i18n.t indirectly: route metas
//    (titleKey), ThemeSwitch options (labelKey), StatCard/toast payloads (key)
const PROP_KEY_RE = /\b(?:titleKey|labelKey|key)\s*:\s*'([a-zA-Z0-9_]+)'/g

for (const file of files) {
  const source = readFileSync(file, 'utf8')
  const relative = file.slice(root.length + 1)
  if (relative.endsWith('stores\\i18n.js') || relative.endsWith('stores/i18n.js')) continue
  const used = [
    ...[...source.matchAll(USE_RE)].map((m) => m[1]),
    ...[...source.matchAll(PROP_KEY_RE)].map((m) => m[1]),
  ]
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

// 3. dynamic families: keys built via template literals that no static scan
//    can enumerate. Each entry must name the constructing site so a rename
//    there has a matching review here.
const DYNAMIC_KEY_FAMILIES = [
  { prefix: 'verdict_', builtBy: 'web/src/utils/verdict.js: t(`verdict_${statusKey}`)' },
  { prefix: 'diff_', builtBy: 'web/src/views/ProblemDetail.vue: t(`diff_${level}`)' },
]

// 4. server-driven keys: the backend sends message_key on every domain error
//    and the frontend renders i18n.t(keyFromServer) - invisible to a source
//    scan by design. Parse lc/i18n.py instead of hand-copying the list so
//    the guard tracks the backend catalog automatically; tests/test_i18n.py
//    guards the same set from the Python side.
function extractServerMessageKeys() {
  const keys = new Set()
  const source = readFileSync(join(root, '..', 'lc', 'i18n.py'), 'utf8')
  for (const match of source.matchAll(/^ {8}"([a-zA-Z0-9_]+)":/gm)) {
    keys.add(match[1])
  }
  return keys
}

let serverKeys
try {
  serverKeys = extractServerMessageKeys()
} catch (err) {
  console.error(`cannot read lc/i18n.py for server-driven key extraction: ${err}`)
  process.exit(1)
}
if (serverKeys.size === 0) {
  console.error(
    'server key extraction found 0 keys - lc/i18n.py no longer matches the ' +
      'extraction regex (8-space-indented quoted keys); fix the regex'
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

const literalUsed = new Set()
for (const [file, used] of usedByFile) {
  for (const key of used) {
    if (!zhKeys.has(key)) {
      console.error(`${file}: t('${key}') has no catalog entry`)
      failed = true
    }
    literalUsed.add(key)
  }
}

// reverse direction: zh/en key sets are verified identical above, so one
// reachability pass over zh covers both locales
const reachable = new Set([...literalUsed, ...serverKeys])
for (const family of DYNAMIC_KEY_FAMILIES) {
  for (const key of zhKeys) {
    if (key.startsWith(family.prefix)) reachable.add(key)
  }
}
const dead = [...zhKeys].filter((key) => !reachable.has(key))
if (dead.length) {
  console.error(
    'catalog keys nothing can reach (dead copy - remove them or wire them up):'
  )
  for (const key of dead) console.error(`  ${key}`)
  failed = true
}

if (failed) process.exit(1)
console.log(
  `i18n ok: ${zhKeys.size} keys, ${usedByFile.size} files scanned, ` +
    `${serverKeys.size} server-driven keys, all usages covered in both locales, no dead keys`
)
