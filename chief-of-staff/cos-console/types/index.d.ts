// What the supervisor's `--console` writes (orchestrating-agents' omnigent_agent.py, schema cos-state/1):
// only the fields this mod reads.
export type Lead = {
  title?: string
  state?: string
  label?: { line?: string; at?: string }
}
export type State = { schema: string; written_at: number; leads: Record<string, Lead> }
export type LeadEvent = { at: number; session: string; kind?: string; line?: string; action?: string; why?: string }

declare module 'claude-code' {
  interface PluginState {
    'cos-console': { state: State | null; problem: string | null; seen: number }
  }
}
