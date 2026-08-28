// Copies the Vite build output into server/webdist — the directory the
// Python wheel packages as package data. Before this script the copy existed
// only as a POSIX-only shell snippet in docs/zh/DEVELOPMENT.md, so nothing
// reproducible produced a shippable tree and the packaging contract was
// never exercised (a forgotten copy step shipped a wheel whose UI was a
// JSON hint telling the user to run npm).
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = resolve(webRoot, '..')
const source = join(webRoot, 'dist')
const target = join(repoRoot, 'server', 'webdist')

if (!existsSync(join(source, 'index.html'))) {
  console.error('web/dist/index.html not found - run `npm run build` first')
  process.exit(1)
}
rmSync(target, { recursive: true, force: true })
mkdirSync(target, { recursive: true })
cpSync(source, target, { recursive: true })
console.log(`copied ${source} -> ${target}`)
