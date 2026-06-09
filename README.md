# agent-skills

Krzysztof Zarzycki's plugin marketplace for Claude Code.

## Plugins

| Plugin | What it's for |
|---|---|
| **workflow** | Persistent project workspaces, subagent orchestration, a read-only main-thread mode, session search, and learning consolidation. |
| **research** | Deep-research orchestration — parallel multi-source web search producing cited reports, plus delegation to hosted research assistants. |
| **engineering** | Safely vetting and adopting third-party code, and capturing a project's conventions. |
| **content** | Understanding and reproducing a person's writing voice for outreach, content, and proposals. |
| **experimental** | Skills under active iteration. **Contract:** anything here may change, break, or be removed at any time — not held to the stability of the other plugins. |

Each plugin's skills self-describe once installed (`/plugin` → browse). Descriptions
here stay plugin-level on purpose — see [Conventions](#conventions).

## Install

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
- Plugin versions in `<plugin>/.claude-plugin/plugin.json` follow semver. Bump on every PR with changes.
- PR titles use Conventional Commits (`feat:`, `fix:`, `chore:`, etc.).
- Each plugin can be installed independently. Cross-plugin dependencies are documented in the plugin's README.
