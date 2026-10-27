import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { LeadEvent, State } from '../types'

const PANE = 'cos-leads'
const POLL_MS = 15_000
// ponytail: four of the supervisor's polls; a schema field for its poll budget would be exact.
const STALE_S = 120
const EVENTS_KEPT = 50

const state = atom({ plugin: 'cos-console', key: 'state' } as const, null)
const problem = atom({ plugin: 'cos-console', key: 'problem' } as const, null)
// When the last owner message got its digest: events after it are the ones the CoS has not seen.
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
    if (s.schema !== 'cos-state/1' || typeof s.leads !== 'object') throw new Error(`schema ${s.schema}`)
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

async function events($: EngineInterface, registry: string, since: number): Promise<LeadEvent[]> {
  const text = await $.fs.read(sibling(registry, '.events.jsonl')).catch(() => '')
  return text
    .split('\n')
    .flatMap(line => {
      try {
        return [JSON.parse(line) as LeadEvent]
      } catch {
        return []
      }
    })
    .filter(ev => ev.at > since)
    .slice(-EVENTS_KEPT)
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
    const now = Math.round((await $.clock.now()) / 1000)
    const since = await read($, seen)
    const s = await refresh($, registry)
    const why = await read($, problem)
    const missed = await events($, registry, since)
    await update($, seen, () => now)
    const lines = [
      'cos-console: the leads now' + (why ? ` (${why})` : '') + ':',
      ...(s ? rows(s).map(r => `- ${r}`) : ['- no state']),
    ]
    if (missed.length > 0) {
      lines.push('Supervisor events since your last message:')
      lines.push(...missed.map(ev => `- ${ev.line.split('\n')[0]}${ev.action ? ` → ${ev.action}` : ''}`))
    }
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
