// The deterministic layer: which supervisor notices need no model at all.
// Pure functions, so the same table can be ported to the supervisor (Python) unchanged.

export type Notice = { session: string; title: string; state: string; last: string }
export type Route = { route: 'absorb' | 'cos' | 'owner' | 'triage'; kind: string; why: string }

const HEAD = /^Supervisor: (?:\d{4}-\d\d-\d\d \d\d:\d\d:\d\d )?([0-9a-f]{32})(?: (.*?))?(?: \(\d+ queued inputs?\))?: (.*)$/

export function parse(text: string): Notice | null {
  const [head, ...rest] = text.split('\n')
  const m = HEAD.exec(head ?? '')
  if (!m) return null
  const last = rest.join('\n').replace(/^last message: /, '')
  return { session: m[1] ?? '', title: m[2] ?? '', state: m[3] ?? '', last }
}

const ENDING = /^\W*(DONE|USER NEEDED|PARKED|STILL WORKING)\b/m
// A lead that names what it waits on is not stalled: its worker, verifier or CI wakes it.
const WAITING = /\b(waiting (on|for)|waits on|until (ci|the verifier|the worker)|in review|ci (is )?running)\b/i
const REPORT_PATH = /^\s*\S+\.md\s*$/

export function route(n: Notice): Route {
  const ending = ENDING.exec(n.last)?.[1]
  if (n.state === 'archived') return { route: 'absorb', kind: 'archived', why: 'archived: drop its row' }
  if (n.state.startsWith('blocked on a prompt')) return { route: 'owner', kind: 'prompt', why: 'only the owner approves' }
  if (n.state.startsWith('failed')) return { route: 'cos', kind: 'failed', why: 'revive once, then the owner' }
  if (ending === 'PARKED') return { route: 'absorb', kind: 'parked', why: 'waits on host capacity' }
  if (ending === 'DONE') return { route: 'cos', kind: 'done', why: 'tell the owner its result, wake leads waiting on it' }
  if (ending === 'USER NEEDED') return { route: 'triage', kind: 'user-needed', why: 'a standing decision may cover it' }
  if (ending === 'STILL WORKING' && WAITING.test(n.last)) return { route: 'absorb', kind: 'waiting', why: 'names its wait' }
  if (REPORT_PATH.test(n.last)) return { route: 'cos', kind: 'report', why: 'ended with a report path: read its first line' }
  return { route: 'triage', kind: 'quiet', why: 'no ending: stall or wait' }
}

// The small model's question: one notice, the standing decisions, no transcript.
export function triagePrompt(n: Notice, decisions: string): string {
  return [
    'You route one event for a chief-of-staff agent. Answer with one line of JSON only:',
    '{"route":"absorb"|"cos"|"owner","why":"<10 words>"}.',
    'absorb: nothing to do now (the lead names what it waits on, or is mid-work).',
    "cos: the chief must act (nudge a stall, answer under a standing decision, report a result).",
    'owner: only the owner can decide (not reversible, or no standing decision covers it).',
    'When unsure, answer cos.',
    `Standing decisions:\n${decisions || '(none)'}`,
    `Event: lead ${n.title} (${n.session}) ${n.state}.`,
    `Its last message:\n${n.last.slice(0, 2000)}`,
  ].join('\n')
}

export function parseTriage(text: string): Route['route'] {
  const m = /\{[^}]*"route"\s*:\s*"(absorb|cos|owner)"/.exec(text)
  return (m?.[1] as Route['route']) ?? 'cos' // ponytail: anything unparseable escalates
}
