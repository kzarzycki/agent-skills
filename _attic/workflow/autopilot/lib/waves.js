// Pure: tasks -> array of waves (each an array of task ids).
// A wave = tasks whose deps are all in earlier waves AND whose fileScope is
// pairwise-disjoint from others placed in the same wave. Overlapping scopes are
// pushed to a later wave so parallel implementers never write the same file.

export function deriveWaves(tasks) {
  const byId = new Map(tasks.map((t) => [t.id, t]))
  for (const t of tasks) {
    for (const d of t.deps || []) {
      if (!byId.has(d)) throw new Error(`unknown dependency: ${d} (task ${t.id})`)
    }
  }
  const placed = new Set()
  const waves = []
  let guard = tasks.length + 1
  while (placed.size < tasks.length) {
    if (guard-- <= 0) throw new Error('dependency cycle detected')
    const ready = tasks.filter(
      (t) => !placed.has(t.id) && (t.deps || []).every((d) => placed.has(d))
    )
    if (!ready.length) throw new Error('dependency cycle detected')
    const wave = []
    const usedFiles = new Set()
    for (const t of ready) {
      const scope = t.fileScope || []
      const clash = scope.some((f) => usedFiles.has(f))
      if (clash) continue // defer to a later wave
      wave.push(t.id)
      scope.forEach((f) => usedFiles.add(f))
    }
    wave.forEach((id) => placed.add(id))
    waves.push(wave)
  }
  return waves
}
