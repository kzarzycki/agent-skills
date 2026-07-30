# agent-skills

A distribution monorepo for independently versioned coding-agent capability
packs. APM is the project installation path; native agent manifests provide
optional adapters.

## Plugins

| Plugin | What it's for |
|---|---|
| **workflow** | Persistent project workspaces, subagent orchestration, a read-only main-thread mode, session search, learning consolidation, and durable human-gated workflows. |
| **research** | Deep-research orchestration — parallel multi-source web search producing cited reports, plus delegation to hosted research assistants. |
| **engineering** | Safely vetting and adopting third-party code, and capturing a project's conventions. |
| **content** | Understanding and reproducing a person's writing voice for outreach, content, and proposals. |
| **experimental** | Skills under active iteration. **Contract:** anything here may change, break, or be removed at any time — not held to the stability of the other plugins. |

Each plugin's skills self-describe once installed (`/plugin` → browse). Descriptions
here stay plugin-level on purpose — see [Conventions](#conventions).

## Install engineering with APM

Add one project dependency:

```yaml
dependencies:
  apm:
    - git: kzarzycki/agent-skills/engineering
      ref: ^0.2.0
```

```bash
apm install
apm compile --validate
```

APM compiles for the coding agents declared by the project and resolves
`^0.2.0` from package-scoped tags such as `engineering-v0.2.0`.

## Install native Claude plugins

Add the marketplace, then install plugins by name.

```bash
# In Claude Code:
/plugin marketplace add kzarzycki/agent-skills
/plugin install workflow@kzarzycki-agent-skills
/plugin install research@kzarzycki-agent-skills
/plugin install engineering@kzarzycki-agent-skills
/plugin install content@kzarzycki-agent-skills
/plugin install experimental@kzarzycki-agent-skills
```

Pick the plugins you want. Each is independent.

The imported `engineering` payload is generated from its pinned vendir lock,
then qualified and patched. Edit `engineering/vendir.yml` or the owned patch
series; do not edit imported skill files directly.

## Local Development

Clone, register the local checkout as a marketplace, and iterate without pushing:

```bash
git clone https://github.com/kzarzycki/agent-skills ~/dev/agent-skills

# In Claude Code:
/plugin marketplace add /Users/yourname/dev/agent-skills
```

To pull in changes from a local edit without pushing first, see `.claude/CLAUDE.md` for the `git remote add local` + fast-forward merge pattern.


## Conventions

- **Descriptions stay plugin-level.** `marketplace.json` and each `plugin.json`
  describe the *plugin's* purpose — they don't enumerate individual skills, which
  change too often to keep in sync. Per-skill detail lives in each skill's own
  `SKILL.md` (and surfaces in the `/plugin` browser).
- **`experimental` is unstable by contract.** Skills there may change or be
  removed without notice; they graduate into a stable plugin once settled. Pin a
  commit if you depend on one.
- Capability-pack versions in `<pack>/apm.yml` and
  `<pack>/.claude-plugin/plugin.json` follow semver. Tags are package-scoped:
  `<pack>-vX.Y.Z`.
- PR titles use Conventional Commits (`feat:`, `fix:`, `chore:`, etc.).
- Each plugin can be installed independently. Cross-plugin dependencies are documented in the plugin's README.
