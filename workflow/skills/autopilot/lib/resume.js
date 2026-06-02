export const PHASES = ['plan', 'plan-review', 'execute', 'code-review', 'verify', 'finish']

export function nextPhase(cur) {
  const i = PHASES.indexOf(cur)
  if (i < 0 || i === PHASES.length - 1) return null
  return PHASES[i + 1]
}

export function bumpRetry(state, phase) {
  return { ...state, [phase]: (state[phase] || 0) + 1 }
}

export function retriesLeft(state, phase, budget) {
  return budget - (state[phase] || 0)
}
