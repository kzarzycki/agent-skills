import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { LeadEvent, State } from '../types'

const PANE = 'cos-leads'
const POLL_MS = 15_000
// ponytail: four of the supervisor's polls; a schema field for its poll budget would be exact.
const STALE_S = 120

const state = atom({ plugin: 'cos-console', key: 'state' } as const, null)
const problem = atom({ plugin: 'cos-console', key: 'problem' } as const, null)
// How many lines of the event log earlier owner messages carried: the lines after them are the ones the CoS
// has not seen. A line count, not a time, so an event stamped in the same second as a message is not lost.
const seen = atom({ plugin: 'cos-console', key: 'seen' } as const, 0)

const sibling = (registry: string, suffix: string) => registry.replace(/(\.[^./]*)?$/, suffix)

function count(s: State): string {
  const leads = Object.values(s.leads)
  const n = (st: string) => leads.filter(l => l.state === st).length
  return `leads ${leads.length}: ${n('running')} running, ${n('blocked')} blocked, ${n('failed')} failed`
}

function rows(s: State): string[] {
  return Object.entries(s.leads)
    .filter(([, l]) => l.state !== 'archived')
    .map(([id, l]) => `${l.title || id.slice(0, 8)}: ${l.label?.line ?? l.state ?? 'unknown'}`)
}

async function refresh($: EngineInterface, registry: string): Promise<State | null> {
  const file = sibling(registry, '.state.json')
  try {
    const s = JSON.parse(await $.fs.read(file)) as State
    if (s.schema !== 'cos-state/1' || typeof s.leads !== 'object' || s.leads === null) throw new Error(`schema ${s.schema}`)
    const age = Math.round((await $.clock.now()) / 1000 - s.written_at)
    const stale = age > STALE_S ? `state is ${age}s old: is the supervisor running?` : null
    await update($, state, () => s)
    await update($, problem, () => stale)
    $.ui.status(stale ? `cos: STALE ${age}s` : `cos: ${count(s)}`)
    return s
  } catch (e) {
    await update($, problem, () => `cannot read ${file}: ${String(e).slice(0, 120)}`)
    $.ui.status('cos: no state file')
    return null
  }
}

/** The events past the first `seen` lines of the log, and the line count to store once they are attached; null
 * when the log cannot be read, so nothing counts as seen. */
async function events($: EngineInterface, registry: string, seen: number): Promise<{ missed: LeadEvent[]; upTo: number } | null> {
  let text: string
  try {
    text = await $.fs.read(sibling(registry, '.events.jsonl'))
  } catch {
    return null
  }
  // The last piece has no newline yet (empty, or a line the supervisor is still appending): the next message gets it.
  const lines = text.split('\n').slice(0, -1)
  // A log shorter than the count was replaced: read it from the start.
  const from = lines.length < seen ? 0 : seen
  const missed = lines
    .slice(from)
    .flatMap(line => {
      try {
        const ev: unknown = JSON.parse(line)
        return ev !== null && typeof ev === 'object' ? [ev as LeadEvent] : []
      } catch {
        return []
      }
    })
  return { missed, upTo: lines.length }
}

export const register: Register = (on, options) => {
  const registry = String(options.registry ?? 'leads.registry')

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'leads', description: 'Show every lead the supervisor follows' })
    await refresh($, registry)
    $.clock.every(POLL_MS, () => refresh($, registry))
    return next(e)
  })

  on('command.run', { command: 'leads' }, async $ => {
    const s = await refresh($, registry)
    const why = await read($, problem)
    void $.ui.open({ id: PANE, title: 'Leads' })
    return { text: [why, s ? [count(s), ...rows(s)].join('\n') : 'no state yet'].filter(Boolean).join('\n') }
  })

  // An owner's message gets the leads' status and the events since the last one, so "how's it
  // going?" needs no tool call. A supervisor post passes untouched: it carries its own lead's news.
  on('prompt.submit', async ($, e, next) => {
    if (e.command || e.text.startsWith('Supervisor')) return next(e)
    const s = await refresh($, registry)
    const why = await read($, problem)
    const log = await events($, registry, await read($, seen))
    const lines = [
      'cos-console: the leads now' + (why ? ` (${why})` : '') + ':',
      ...(s ? rows(s).map(r => `- ${r}`) : ['- no state']),
    ]
    if (!log) lines.push('Supervisor events: cannot read the event log')
    if (log && log.missed.length > 0) {
      lines.push('Supervisor events since your last message:')
      lines.push(...log.missed.map(ev => `- ${String(ev.line ?? ev.kind).split('\n')[0]}${ev.action ? ` → ${ev.action}` : ''}`))
    }
    if (log) await update($, seen, () => log.upTo)
    return next({ ...e, context: [...(e.context ?? []), lines.join('\n')] })
  }).catch(($, e, next) => next(e)) // fail open: the message reaches the model as without the mod

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const s = await read($, state)
    const why = await read($, problem)
    const width = Math.max(20, (e.props.bodyColumns ?? 80) - 2)
    return (
      <Box flexDirection="column">
        {why && <Text color="red">{why}</Text>}
        {!s && <Text dimColor>No state yet.</Text>}
        {s && <Text bold>{count(s)}</Text>}
        {s && rows(s).map(r => <Text>{r.slice(0, width)}</Text>)}
      </Box>
    )
  })
}
