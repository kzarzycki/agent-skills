import { expect, mock, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

type On = Parameters<TestBody>[1]

const NOW = 1_792_500_000 // seconds
const LEAD = 'ba7c500f8f1d432f9352096af130c3c8'
const STATE = {
  schema: 'cos-state/1',
  written_at: NOW - 10,
  leads: {
    [LEAD]: { title: 's431-lead', state: 'running', label: { line: 'running · waits on CI', at: String(NOW - 10) } },
    ['f'.repeat(32)]: { title: 's52-lead', state: 'turn ended', label: { line: 'turn ended: DONE: #52 merged', at: String(NOW - 30) } },
    ['0'.repeat(32)]: { title: 'gone', state: 'archived' },
  },
}
const EVENT = (at: number, line: string) => JSON.stringify({ at, id: `e${at}`, session: LEAD, kind: 'ended', line, action: 'record' })

/** The files beneath the plugin: each path's text, or a read that fails like a missing file. */
function files(on: On, byPath: Record<string, string>, reads: string[] = []) {
  // The engine hands a hook the path resolved against the session's folder.
  on('fs.read', (_, e) => {
    reads.push(e.path)
    const name = e.path.split('/').at(-1)!
    if (!(name in byPath)) throw new Error(`ENOENT: ${e.path}`)
    return { value: byPath[name] } as never
  })
  on('ui.status', () => ({ value: undefined }) as never)
}

function context(on: On) {
  const seen: { text: string; context?: readonly string[] }[] = []
  on('prompt.submit', (_, e) => {
    seen.push({ text: e.text, context: e.context })
    return { text: e.text }
  })
  return seen
}

const submit = ($: Parameters<TestBody>[0], text: string) =>
  $.prompt.submit({ text, wait: false, origin: { kind: 'unclassified' } })

test('an owner message gets every live lead and the events since the last one', async ($, on) => {
  mock.clock(on, { now: NOW * 1000 })
  files(on, {
    'leads.state.json': JSON.stringify(STATE),
    'leads.events.jsonl': [EVENT(NOW - 60, 'turn ended: STILL WORKING: waiting on CI'), 'not json', ''].join('\n'),
  })
  const seen = context(on)

  await submit($, "how's it going?")
  await submit($, 'and now?')

  expect(seen[0]!.text).toBe("how's it going?")
  const first = seen[0]!.context!.at(-1)!
  expect(first).toMatch(/s431-lead: running · waits on CI/)
  expect(first).toMatch(/s52-lead: turn ended: DONE: #52 merged/)
  expect(first).not.toMatch(/gone/)
  expect(first).toMatch(/events since your last message:\n- turn ended: STILL WORKING: waiting on CI → record/)
  // The second message comes after every event: it gets the leads, not the same events again.
  expect(seen[1]!.context!.at(-1)!).not.toMatch(/events since/)
})

test('a supervisor post passes through untouched', async ($, on) => {
  mock.clock(on, { now: NOW * 1000 })
  const reads: string[] = []
  files(on, { 'leads.state.json': JSON.stringify(STATE) }, reads)
  const seen = context(on)

  for (const text of [`Supervisor: ${LEAD} s431-lead: turn ended`, `Supervisor [act] b-1: 1 event\n- ${LEAD} failed`]) {
    await submit($, text)
  }

  expect(seen.map(s => [s.text, s.context])).toEqual([
    [`Supervisor: ${LEAD} s431-lead: turn ended`, undefined],
    [`Supervisor [act] b-1: 1 event\n- ${LEAD} failed`, undefined],
  ])
  expect(reads).toEqual([])
})

test('a missing or stale state file shows in the status line', async ($, on) => {
  mock.clock(on, { now: NOW * 1000 })
  const lines: (string | undefined)[] = []
  let state: string | null = null
  on('fs.read', (_, e) => {
    if (state === null || !e.path.endsWith('/leads.state.json')) throw new Error('ENOENT')
    return { value: state } as never
  })
  on('ui.status', (_, e) => {
    lines.push(e.text)
    return { value: undefined } as never
  })
  on('command.register', () => ({ value: { command: 'leads' } }) as never)
  on('ui.open', () => ({ value: { isPlaced: true } }) as never)
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  state = JSON.stringify({ ...STATE, written_at: NOW - 600 })
  await $.command.run({ command: 'leads', args: '' } as never)
  state = JSON.stringify(STATE)
  await $.command.run({ command: 'leads', args: '' } as never)

  expect(lines).toEqual(['cos: no state file', 'cos: STALE 600s', 'cos: leads 3: 1 running, 0 blocked, 0 failed'])
})

test('a broken state file lets the message through', async ($, on) => {
  mock.clock(on, { now: NOW * 1000 })
  files(on, { 'leads.state.json': '{ not json', 'leads.events.jsonl': '' })
  const seen = context(on)

  await submit($, 'status?')

  expect(seen).toHaveLength(1)
  expect(seen[0]!.text).toBe('status?')
  expect(seen[0]!.context!.at(-1)!).toMatch(/cannot read leads.state.json/)
})

test('every event reaches an owner message once: none capped, none lost to its second or to a failed read', async ($, on) => {
  mock.clock(on, { now: NOW * 1000 })
  const log: string[] = Array.from({ length: 60 }, (_, i) => EVENT(NOW, `event ${i}`))
  let readable = true
  on('fs.read', (_, e) => {
    if (e.path.endsWith('/leads.state.json')) return { value: JSON.stringify(STATE) } as never
    if (!readable) throw new Error('EAGAIN')
    return { value: log.map(l => l + '\n').join('') + '{"at": 1' } as never // the last line is still being written
  })
  on('ui.status', () => ({ value: undefined }) as never)
  const seen = context(on)
  const delivered = () => seen.flatMap(s => s.context!.at(-1)!.match(/^- (event \d+|no line).*$/gm) ?? [])

  await submit($, 'one') // all 60, the half-written line held back
  log.push(EVENT(NOW, 'event 60')) // the same second as the message before
  readable = false
  await submit($, 'two') // the log cannot be read: nothing counts as seen
  readable = true
  log.push(JSON.stringify({ at: NOW, kind: 'no line' }))
  await submit($, 'three')

  expect(seen[1]!.context!.at(-1)!).toMatch(/cannot read the event log/)
  expect(delivered()).toEqual([...Array.from({ length: 61 }, (_, i) => `- event ${i} → record`), '- no line'])
})

test('a state file whose leads are null shows as unreadable', async ($, on) => {
  mock.clock(on, { now: NOW * 1000 })
  files(on, { 'leads.state.json': JSON.stringify({ ...STATE, leads: null }), 'leads.events.jsonl': '' })
  const seen = context(on)

  await submit($, 'status?')

  expect(seen[0]!.context!.at(-1)!).toMatch(/cannot read leads.state.json.*\n- no state/)
})

test('a hook that throws fails open: the message reaches the model as typed', async ($, on) => {
  mock.clock(on, { now: NOW * 1000 })
  // An event log read that answers a number: splitting it throws inside the hook.
  on('fs.read', (_, e) => ({ value: e.path.endsWith('.events.jsonl') ? 42 : JSON.stringify(STATE) }) as never)
  on('ui.status', () => ({ value: undefined }) as never)
  const seen = context(on)

  await submit($, 'status?')

  expect(seen).toEqual([{ text: 'status?', context: undefined }])
})
