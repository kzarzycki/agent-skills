import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { CosEvent, CosLead, CosStatus } from '../types'
import { parse, parseTriage, route, triagePrompt } from './rules'

const PANE = 'cos-leads'
const status = atom({ plugin: 'cos-console', key: 'status' } as const, null)
const error = atom({ plugin: 'cos-console', key: 'error' } as const, null)
const events = atom({ plugin: 'cos-console', key: 'events' } as const, [])
const POLL_MS = 15_000
const STALE_S = 120 // ponytail: twice the supervisor's poll budget; make it the schema's own field

const MARK: Record<CosLead['state'], string> = {
  running: '●', idle: '○', blocked: '!', failed: '✗', archived: '·', unknown: '?',
}

function summary(s: CosStatus): string {
  const n = (st: string) => s.leads.filter(l => l.state === st).length
  return `leads ${s.leads.length}: ${n('running')} running, ${n('idle')} idle, ${n('blocked')} blocked, ${n('failed')} failed`
}

function table(s: CosStatus): string {
  return s.leads
    .map(l => `${MARK[l.state] ?? '?'} ${l.id.slice(0, 8)} ${l.title.slice(0, 40)} [${l.host ?? '?'}] ${l.waits_on?.slice(0, 60) ?? ''}`)
    .join('\n')
}

async function refresh($: EngineInterface, file: string) {
  try {
    const s = JSON.parse(await $.fs.read(file)) as CosStatus
    const age = Math.round((await $.clock.now()) / 1000 - s.written_at)
    await update($, status, () => s)
    await update($, error, () => (age > STALE_S ? `status is ${age}s old: is the supervisor running?` : null))
    $.ui.status(age > STALE_S ? `cos: STALE ${age}s` : `cos: ${summary(s)}`)
  } catch (e) {
    await update($, error, () => `cannot read ${file}: ${String(e).slice(0, 120)}`)
    $.ui.status('cos: no status file')
  }
}

export const register: Register = (on, options) => {
  const file = String(options.statusFile ?? 'tmp/loop/cos-status.json')
  const model = String(options.triageModel ?? 'haiku')

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'leads', description: 'Show every lead the chief of staff follows' })
    await refresh($, file)
    $.clock.every(POLL_MS, () => refresh($, file))
    return next(e)
  })

  on('command.run', { command: 'leads' }, async $ => {
    await refresh($, file)
    const s = await read($, status)
    const err = await read($, error)
    if (s) void $.ui.open({ id: PANE, title: 'Leads' })
    return { text: [err, s ? `${summary(s)}\n${table(s)}` : 'no status yet'].filter(Boolean).join('\n') }
  })

  // The win: a routine notice never becomes a model turn. The owner still sees it in the
  // chat (Omnigent stored the posted message); the model learns of it at its next real turn.
  on('prompt.submit', async ($, e, next) => {
    const notice = parse(e.text)
    const now = Math.round((await $.clock.now()) / 1000)
    if (!notice) {
      // An owner's message: hand the model the events it slept through, then forget them.
      const missed = (await read($, events)).filter(ev => ev.route === 'absorb')
      await update($, events, () => [])
      if (missed.length === 0) return next(e)
      const digest = missed.map(ev => `- ${ev.session.slice(0, 8)} ${ev.kind}: ${ev.why}`).join('\n')
      return next({ ...e, context: [...(e.context ?? []), `cos-console: handled without you since your last turn:\n${digest}`] })
    }
    let r = route(notice)
    if (r.route === 'triage') {
      const decisions = await $.fs.read('board.md').then(b => b.split('## Standing decisions')[1]?.split('\n## ')[0] ?? '', () => '')
      const answer = await $.model.complete({ model, prompt: triagePrompt(notice, decisions), maxTokens: 100, effort: 'low', timeoutMs: 20_000 })
      const picked = answer.isAnswered ? parseTriage(answer.text) : 'cos'
      r = { ...r, route: picked, why: `${model}: ${answer.isAnswered ? answer.text.trim().slice(0, 120) : answer.reason}` }
    }
    await update($, events, list => [...list, { at: now, session: notice.session, kind: r.kind, route: r.route, why: r.why } as CosEvent].slice(-200))
    if (r.route !== 'cos') {
      $.ui.toast(`cos-console: ${r.kind} for ${notice.title || notice.session.slice(0, 8)} (${r.route})`)
      // Claude puts a dropped prompt back in the box; Omnigent re-sends Enter while its pasted
      // draft is still there, so clear it once the drop has landed.
      $.clock.after(300, () => $.prompt.fill({ text: '', mode: 'replace' }))
      return { drop: `cos-console: ${r.route} ${r.kind}: ${r.why}` }
    }
    // Escalated: give the model the lead's row so it skips the `status` call.
    const lead = (await read($, status))?.leads.find(l => l.id === notice.session)
    const row = lead ? `cos-console: this lead's status row: ${JSON.stringify(lead)}` : 'cos-console: lead not in the status file'
    return next({ ...e, context: [...(e.context ?? []), `cos-console routed this as ${r.kind}: ${r.why}`, row] })
  }).catch(($, e, next) => next(e)) // fail open: the notice reaches the model, as without the mod

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const s = await read($, status)
    const err = await read($, error)
    const evs = (await read($, events)).slice(-5)
    const width = Math.max(20, (e.props.bodyColumns ?? 80) - 2)
    return (
      <Box flexDirection="column">
        {err && <Text color="red">{err}</Text>}
        {!s && <Text dimColor>No status yet.</Text>}
        {s && <Text bold>{summary(s)}</Text>}
        {s?.leads.map(l => (
          <Text key={l.id} dimColor={l.state === 'archived'}>
            {`${MARK[l.state] ?? '?'} ${l.id.slice(0, 8)} ${l.title} · ${l.waits_on ?? l.last_line ?? ''}`.slice(0, width)}
          </Text>
        ))}
        {evs.length > 0 && <Text dimColor>handled: {evs.map(ev => `${ev.kind}→${ev.route}`).join(', ')}</Text>}
      </Box>
    )
  })
}
