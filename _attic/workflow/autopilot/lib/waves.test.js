import { test } from 'node:test'
import assert from 'node:assert/strict'
import { deriveWaves } from './waves.js'

const t = (id, deps, fileScope) => ({ id, deps, fileScope })

test('independent disjoint tasks form one wave', () => {
  const tasks = [t('a', [], ['x.js']), t('b', [], ['y.js'])]
  assert.deepEqual(deriveWaves(tasks), [['a', 'b']])
})

test('dependency forces a later wave', () => {
  const tasks = [t('a', [], ['x.js']), t('b', ['a'], ['y.js'])]
  assert.deepEqual(deriveWaves(tasks), [['a'], ['b']])
})

test('overlapping fileScope serializes within a level', () => {
  const tasks = [t('a', [], ['x.js']), t('b', [], ['x.js'])]
  const waves = deriveWaves(tasks)
  assert.equal(waves.length, 2)
  assert.deepEqual(waves.flat().sort(), ['a', 'b'])
})

test('throws on a dependency cycle', () => {
  const tasks = [t('a', ['b'], ['x.js']), t('b', ['a'], ['y.js'])]
  assert.throws(() => deriveWaves(tasks), /cycle/i)
})

test('throws on unknown dependency id', () => {
  const tasks = [t('a', ['ghost'], ['x.js'])]
  assert.throws(() => deriveWaves(tasks), /unknown/i)
})
