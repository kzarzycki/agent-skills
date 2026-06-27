// Pure: given the files a plan will touch and the repo's file list, return the
// CLAUDE.md files (root + every touched dir and its ancestors) and all
// .claude/rules entries. The engine reads + injects these as the "rules bundle".
// .claude/rules path-scope filtering is deliberately conservative: include all,
// let the consuming agent apply scope.

function ancestorDirs(filePath) {
  const parts = filePath.split('/')
  parts.pop() // drop filename
  const dirs = ['']
  let acc = ''
  for (const p of parts) {
    acc = acc ? `${acc}/${p}` : p
    dirs.push(acc)
  }
  return dirs // '' represents repo root
}

export function gatherRulePaths(touchedFiles, repoFiles) {
  const repo = new Set(repoFiles)
  const claudeMd = new Set()
  for (const f of touchedFiles) {
    for (const dir of ancestorDirs(f)) {
      const candidate = dir ? `${dir}/CLAUDE.md` : 'CLAUDE.md'
      if (repo.has(candidate)) claudeMd.add(candidate)
    }
  }
  if (repo.has('CLAUDE.md')) claudeMd.add('CLAUDE.md')
  const rules = repoFiles.filter((p) => p.startsWith('.claude/rules/'))
  return { claudeMd: [...claudeMd], rules }
}
