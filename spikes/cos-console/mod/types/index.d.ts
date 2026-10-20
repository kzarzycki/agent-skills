export type CosLead = {
  id: string
  title: string
  host?: string
  state: 'running' | 'idle' | 'blocked' | 'failed' | 'archived' | 'unknown'
  waits_on?: string
  ending?: string | null
  prompt?: string | null
  last_line?: string
  link?: string
}
export type CosStatus = { schema: string; written_at: number; leads: CosLead[] }
export type CosEvent = { at: number; session: string; kind: string; route: 'absorb' | 'cos' | 'owner'; why: string }

declare module 'claude-code' {
  interface PluginState {
    'cos-console': { status: CosStatus | null; error: string | null; events: CosEvent[] }
  }
}
