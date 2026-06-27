// engine.js cannot `import` (Workflow constraint), so it inlines copies of the
// lib functions between `// <inline:NAME>` / `// </inline:NAME>` markers.
// This test extracts each inlined block, evaluates it, and re-runs the lib's
// own behavioral assertions against the copy — catching drift.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { deriveWaves } from './waves.js'
import { gatherRulePaths } from './rules.js'

function extractInline(src, name) {
  const re = new RegExp(`// <inline:${name}>([\\s\\S]*?)// </inline:${name}>`)
  const m = src.match(re)
  if (!m) throw new Error(`inline block not found: ${name}`)
  return m[1]
}

const src = readFileSync(new URL('../engine.js', import.meta.url), 'utf8')

test('engine.js inlines deriveWaves identically to lib', () => {
  const block = extractInline(src, 'waves')
  const fn = new Function(`${block}; return deriveWaves;`)()
  const tasks = [
    { id: 'a', deps: [], fileScope: ['x.js'] },
    { id: 'b', deps: ['a'], fileScope: ['y.js'] },
  ]
  assert.deepEqual(fn(tasks), deriveWaves(tasks))
})

test('engine.js inlines gatherRulePaths identically to lib', () => {
  const block = extractInline(src, 'rules')
  const fn = new Function(`${block}; return gatherRulePaths;`)()
  const repoFiles = ['CLAUDE.md', 'src/CLAUDE.md', '.claude/rules/a.md', 'README.md']
  assert.deepEqual(fn(['src/x.js'], repoFiles), gatherRulePaths(['src/x.js'], repoFiles))
})
