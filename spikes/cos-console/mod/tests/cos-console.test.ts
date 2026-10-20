import { expect, mock, test } from 'claude-code/testing'

import { parse, route } from '../hooks/rules'

const SID = 'ba7c500f8f1d432f9352096af130c3c8'
const notice = (state: string, last: string) => `Supervisor: 2026-10-20 12:00:00 ${SID} android-lead: ${state}\nlast message: ${last}`
const USAGE = { input_tokens: 900, output_tokens: 12, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 }

test('the rules settle routine notices without a model', async () => {
  const r = (state: string, last: string) => route(parse(notice(state, last))!).route
  expect(r('archived', 'x')).toBe('absorb')
  expect(r('turn ended', 'PARKED: host over capacity')).toBe('absorb')
  expect(r('turn ended', 'STILL WORKING: waiting on the verifier')).toBe('absorb')
  expect(r('turn ended', 'DONE: #1637 merged')).toBe('cos')
  expect(r('turn ended', '/home/agent/dev/trinity/tmp/loop/grafana-secret-report.md')).toBe('cos')
  expect(r('blocked on a prompt: Bash(rm -rf x)', 'x')).toBe('owner')
  expect(r('turn ended, quiet 412s', 'Running gates.')).toBe('triage')
  expect(r('turn ended', 'USER NEEDED: which bank?')).toBe('triage')
  expect(parse('please carry on')).toBe(null)
})

test('a routine notice is dropped: no model turn', async ($, on) => {
  mock.clock(on, { now: 1_792_500_000_000 })
  let reached = 0
  on('prompt.submit', ($, e) => { reached += 1; return { text: e.text } })
  const r = await $.prompt.submit({ text: notice('turn ended', 'PARKED: over capacity'), wait: false, origin: { kind: 'unclassified' } })
  expect(reached).toBe(0)
  expect('drop' in r && r.drop).toMatch(/absorb parked/)
})

test('a quiet notice goes to the small model, which may absorb it', async ($, on) => {
  mock.clock(on, { now: 1_792_500_000_000 })
  const asked: string[] = []
  on('model.complete', ($, e) => {
    asked.push(e.model)
    return { value: { isAnswered: true, text: '{"route":"absorb","why":"mid-work, running gates"}', usage: USAGE } } as never
  })
  let reached = 0
  on('prompt.submit', ($, e) => { reached += 1; return { text: e.text } })
  const r = await $.prompt.submit({ text: notice('turn ended, quiet 412s', 'Running gates.'), wait: false, origin: { kind: 'unclassified' } })
  expect(asked).toEqual(['haiku'])
  expect(reached).toBe(0)
  expect('drop' in r && r.drop).toMatch(/haiku/)
})

test('an escalated notice reaches the model with what was routed, and the owner sees what was absorbed', async ($, on) => {
  mock.clock(on, { now: 1_792_500_000_000 })
  const seen: { text: string; context?: readonly string[] }[] = []
  on('prompt.submit', ($, e) => { seen.push({ text: e.text, context: e.context }); return { text: e.text } })
  await $.prompt.submit({ text: notice('archived', 'x'), wait: false, origin: { kind: 'unclassified' } })
  await $.prompt.submit({ text: notice('turn ended', 'DONE: #1637 merged'), wait: false, origin: { kind: 'unclassified' } })
  expect(seen).toHaveLength(1)
  expect(seen[0]!.context?.[0]).toMatch(/routed this as done/)
  await $.prompt.submit({ text: 'how are things?', wait: false, origin: { kind: 'unclassified' } })
  expect(seen[1]!.context?.[0]).toMatch(/handled without you.*\n- ba7c500f archived/)
})

test('the pane says when there is no status file', async ($, on) => {
  mock.clock(on, { now: 1_792_500_000_000 })
  await $.command.run({ command: 'leads' } as never)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'cos-console', surface, component: 'Pane', requestId: 'cos-leads', props: { bodyColumns: 80 } } as never)
    expect(await ui.find({ type: 'Text', text: /cannot read tmp\/loop\/cos-status.json/ })).toBeDefined()
    await ui.unmount()
  }
})
