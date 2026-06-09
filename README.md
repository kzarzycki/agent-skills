# agent-skills

Krzysztof Zarzycki's plugin marketplace for Claude Code. Toolkits covering workflow, research, engineering, and content.

## Plugins

| Plugin | What's inside |
|---|---|
| **workflow** | `flow` (.work/ workspace + subagent delegation), `orchestrator` (restrict main thread to read-only), `find-conversation` (search past CC sessions), `communicating-in-html` (optional enrichment — render reports, interviews, and option/mockup choices as self-contained HTML instead of Markdown). Plus the experimental `/promote-learnings` command. |
| **research** | `deep-research` (multi-source orchestration with Perplexity/Tavily/Exa/Gemini/native search), platform skills for `chatgpt-deep-research`, `claude-ai-deep-research`, `gemini-deep-research`. |
| **engineering** | `audit-third-party-software` (safety audit before installing repos/packages), `context-extractor` (analyze any project, generate CLAUDE.md from observed conventions). |
| **content** | `voice-dna` (extract 8-dim writing style from someone's LinkedIn — useful for stakeholder prep, content writing, proposal personalization). |

## Install

Add the marketplace, then install plugins by name.

```bash
# In Claude Code:
/plugin marketplace add kzarzycki/agent-skills
/plugin install workflow@kzarzycki-agent-skills
/plugin install research@kzarzycki-agent-skills
/plugin install engineering@kzarzycki-agent-skills
/plugin install content@kzarzycki-agent-skills
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

## Highlights

### workflow

`/flow:init` bootstraps a `.work/` workspace per project — a Date-prefixed dir per work stream, append-only `log.md`, idea capture, ITEM.md manifest with research/plan/execute/verify lifecycle. `/orchestrator on` restricts the main thread to read-only and forces all writes through subagents. `communicating-in-html` is an optional, zero-coupling enrichment layer (writing-skills style): load it and the agent renders reports, interviews/intake, and option/mockup choices as self-contained HTML instead of Markdown — wherever a rendered page beats a chat dump; don't load it and every other skill behaves traditionally. Grounded in Thariq Shihipar's *"The Unreasonable Effectiveness of HTML."*

### research

`deep-research` orchestrates parallel agents across web search providers and produces cited reports with confidence scores. Use `chatgpt-deep-research`, `claude-ai-deep-research`, or `gemini-deep-research` to delegate to those platforms' native research UIs.

### engineering

`audit-third-party-software` reads a repo/package/binary and outputs a SAFE/CAUTION/UNSAFE verdict with file:line citations covering telemetry, supply-chain risks, hardcoded credentials, and what the code actually does. `context-extractor` walks any project and writes a CLAUDE.md capturing observed conventions and patterns.

### content

`voice-dna` extracts an 8-dimension style profile from a person's LinkedIn posts — vocabulary fingerprint, signature moves, posting modes, and a Prompt Engineering Guide for AI-assisted writing in that voice. Use it to prep before outreach, draft a tailored proposal, or calibrate an AI co-author to a specific style.

## Conventions

- Plugin versions in `<plugin>/.claude-plugin/plugin.json` follow semver. Bump on every PR with changes.
- PR titles use Conventional Commits (`feat:`, `fix:`, `chore:`, etc.).
- Each plugin can be installed independently. Cross-plugin dependencies are documented in the plugin's README.
