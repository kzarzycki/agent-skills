# Available Research Tools

## Deep Research Channels (primary — use these first)

These tools do their own internal multi-step research. They iterate, search across
many sources, read content, and synthesize findings independently. They are the core
of what makes `/deep-research` deep.

### MCP-based Deep Research

| Tool | What it does |
|------|-------------|
| `perplexity_research` | In-depth multi-source investigation. Iterates internally across many sources. |
| `perplexity_reason` | Step-by-step logical analysis with web grounding and reasoning. |
| `tavily_research` | Multi-step research. Iterates internally, produces thorough findings. |

### Browser-based Deep Research Skills

| Skill | What it does |
|-------|-------------|
| `/gemini-deep-research` | Automates Gemini Deep Research at gemini.google.com. Browses hundreds of sites. Spawns as long-living subagent, communicates via SendMessage. |
| `/chatgpt-deep-research` | Automates ChatGPT Deep Research at chatgpt.com. Uses o3/o4-mini reasoning models. Spawns as context:fork subagent. |
| `/claude-ai-deep-research` | Automates Claude.ai Deep Research at claude.ai. No plan review — starts immediately. Spawns as context:fork subagent. |

---

## Supplementary Tools (for targeted lookups, gap-filling, verification)

These are lighter tools for specific tasks — finding URLs, reading pages, checking facts,
brainstorming angles. Use alongside deep research channels, not instead of them.

### Perplexity MCP
| Tool | What it does |
|------|-------------|
| `perplexity_search` | Web search returning titles, URLs, snippets, dates |
| `perplexity_ask` | AI-answered questions with citations |

### Tavily MCP
| Tool | What it does |
|------|-------------|
| `tavily_search` | Web search with date filtering (`start_date`, `end_date`, `time_range`) and domain filtering |
| `tavily_extract` | Extract clean content from specific URLs |
| `tavily_crawl` | Crawl a website following links |
| `tavily_map` | Map a website's structure |

### Exa MCP
| Tool | What it does |
|------|-------------|
| `web_search_exa` | Semantic/neural search — finds content by meaning, not just keywords. Supports category filtering (company, research paper, people) |
| `crawling` | Crawl and extract clean page content |

### Gemini MCP
| Tool | What it does |
|------|-------------|
| `ask-gemini` | Send a prompt to Gemini 2.5 Pro (different LLM perspective) |
| `brainstorm` | Creative ideation with frameworks (SCAMPER, design thinking, etc.) |

### Native Tools (always available)
| Tool | What it does |
|------|-------------|
| `WebSearch` | Claude's built-in web search — returns page titles and URLs |
| `WebFetch` | Read a URL with a focused question — returns AI-summarized content |
