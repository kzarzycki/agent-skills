import { test } from 'node:test'
import assert from 'node:assert/strict'
import { gatherRulePaths } from './rules.js'

const repoFiles = [
  'CLAUDE.md',
  'src/CLAUDE.md',
  'src/api/CLAUDE.md',
  '.claude/rules/api.md',
  '.claude/rules/db.md',
  'README.md',
]

test('always includes root CLAUDE.md', () => {
  const out = gatherRulePaths(['README.md'], repoFiles)
  assert.ok(out.claudeMd.includes('CLAUDE.md'))
})

test('includes CLAUDE.md in each touched directory and its ancestors', () => {
  const out = gatherRulePaths(['src/api/handler.js'], repoFiles)
  assert.deepEqual(
    out.claudeMd.sort(),
    ['CLAUDE.md', 'src/CLAUDE.md', 'src/api/CLAUDE.md'].sort()
  )
})

test('does not include CLAUDE.md from untouched sibling dirs', () => {
  const out = gatherRulePaths(['src/util.js'], repoFiles)
  assert.ok(!out.claudeMd.includes('src/api/CLAUDE.md'))
})

test('includes all .claude/rules entries', () => {
  const out = gatherRulePaths(['src/util.js'], repoFiles)
  assert.deepEqual(out.rules.sort(), ['.claude/rules/api.md', '.claude/rules/db.md'].sort())
})

test('dedupes when multiple files touch the same dir', () => {
  const out = gatherRulePaths(['src/a.js', 'src/b.js'], repoFiles)
  assert.equal(out.claudeMd.filter((p) => p === 'src/CLAUDE.md').length, 1)
})
