# agent-skills

A distribution monorepo for independently versioned coding-agent capability
packs. APM is the project installation path; native agent manifests provide
optional adapters.

## Plugins

| Plugin | What it's for |
|---|---|
| **research** | Deep-research orchestration — parallel multi-source web search producing cited reports, plus delegation to hosted research assistants. |
| **engineering** | The design, testing, review and browsing skills a coding agent uses, and how it starts and collects other agents. For one release line it also pulls in the five packages below. |
| **gatekeeper** | May this change be built, enter a merge queue or merge: decided from proof on the forge and the team's policy. |
| **loop** | The engineering loop: a lead, workers and an independent verifier take a change from intent to a landed PR. Pulls in `gatekeeper` and `github`. |
| **github** | The GitHub tracker and forge conventions the loop and the gatekeeper run on, with label sync and board moves. Pulls in `gatekeeper`. |
| **chief-of-staff** | One person's view over many leads and repos. Pulls in `loop` and `omnigent`. |
| **omnigent** | Running agents through Omnigent: the backend, operating an install, and its telemetry. |
| **vendoring** | Pulling skills from an upstream repo into a pack by a vendir lock, keeping your own overlays, and releasing it; plus a pre-install audit of a software update. |
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
      ref: ^0.3.0
```

```bash
apm install
apm compile --validate
```

APM compiles for the coding agents declared by the project and resolves
`^0.3.0` from package-scoped tags such as `engineering-v0.3.0`.

## Install native Claude plugins

Add the marketplace, then install plugins by name.

```bash
# In Claude Code:
/plugin marketplace add kzarzycki/agent-skills
/plugin install research@kzarzycki-agent-skills
/plugin install engineering@kzarzycki-agent-skills
/plugin install content@kzarzycki-agent-skills
/plugin install experimental@kzarzycki-agent-skills
```

Pick the plugins you want. Installing one installs the packages it depends on (`docs/layers.md` has the map).

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
- A package declares the packages it uses in both manifests (`dependencies` in `plugin.json` and in `apm.yml`), so installing it installs them.
