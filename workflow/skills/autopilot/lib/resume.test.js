import { test } from 'node:test'
import assert from 'node:assert/strict'
import { PHASES, nextPhase, bumpRetry, retriesLeft } from './resume.js'

test('PHASES is the ordered engine sequence', () => {
  assert.deepEqual(PHASES, ['plan', 'plan-review', 'execute', 'code-review', 'verify', 'finish'])
})

test('nextPhase advances and returns null past the end', () => {
  assert.equal(nextPhase('plan'), 'plan-review')
  assert.equal(nextPhase('verify'), 'finish')
  assert.equal(nextPhase('finish'), null)
})

test('bumpRetry increments per phase and retriesLeft reflects budget', () => {
  let s = {}
  s = bumpRetry(s, 'verify')
  s = bumpRetry(s, 'verify')
  assert.equal(s.verify, 2)
  assert.equal(retriesLeft(s, 'verify', 3), 1)
  assert.equal(retriesLeft(s, 'plan-review', 3), 3)
})
