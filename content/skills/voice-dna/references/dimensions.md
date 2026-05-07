# Style Analysis: Posting Modes & Dimensions Reference

Self-contained reference for subagents performing style analysis on written content (LinkedIn posts, blog posts, etc.). Reading this file alone is sufficient to classify posting modes and analyze all 8 style dimensions.

---

## Part 1: Posting Modes (Classify First)

Before analyzing dimensions, classify each post into exactly one mode. A single author typically has multiple modes — mixing them dilutes the signal. The authentic voice must be analyzed separately from other modes.

| Mode | Description | Analysis Treatment |
|------|-------------|-------------------|
| **Authentic voice** | Original posts in the author's natural voice | Primary analysis target — this IS the style |
| **Quick reshare** | Repost with brief commentary (1-2 sentences) | Separate analysis — reveals topic affinity and editorializing habits |
| **Marketing-provided** | Written by marketing/comms, published under the author's name | Exclude from style analysis — flag as "not authentic" |
| **Event/promo** | Announcements, conference plugs, webinar promos | Analyze separately — blend of authentic voice + promotional format |
| **Thought piece** | Longer, deliberate posts with a thesis | Analyze as premium authentic voice — style shines most here |
| **Minimal/legacy** | Low-effort or old-format posts (likes repackaged, one-liners) | Exclude unless patterns emerge across multiple posts |

### Detecting Marketing-Provided Posts

Flag a post as marketing-provided when you see:
- Overly polished, brand-aligned language inconsistent with the author's other posts
- Heavy use of company-specific CTAs and branded terms
- Tone mismatch with authentic posts (e.g., suddenly corporate when usually casual)
- Emoji/formatting patterns different from the author's usual style

### Mode Classification Procedure

1. Read all posts first before classifying any
2. Identify the author's baseline voice from the majority of posts
3. Flag deviations — posts that feel "off" relative to the baseline
4. Assign modes, then proceed to dimension analysis on authentic voice + thought pieces only

---

## Part 2: The 8 Dimensions

Analyze each dimension independently. For each, place the author on the stated spectrum and cite specific evidence (quotes, patterns, frequencies).

---

### 1. Voice & Tone

**What it captures:** The personality that comes through in the writing.

**Spectrum anchors:**
- Formal ↔ Casual
- Confident ↔ Humble
- Authoritative ↔ Peer-level
- Serious ↔ Playful

**What to look for:**
- How do they address the reader? ("you" vs passive voice, peer vs audience)
- Contractions, colloquialisms, slang?
- How do they handle expertise — speaking from above or alongside?
- Consistency of tone across different topics

**Anti-patterns:** Corporate-speak, motivational poster tone, false humility

---

### 2. Language Register

**What it captures:** Vocabulary choices, complexity, accessibility, and human-sounding markers.

**Spectrum anchors:**
- Simple ↔ Complex vocabulary
- Jargon-heavy ↔ Plain language
- Polished ↔ Raw/unedited feel

**What to look for:**
- Average sentence length and complexity
- Industry jargon frequency — explained or assumed?
- Vocabulary breadth — repetitive or varied?
- **Human-sound markers** (critical for non-native speakers):
  - Natural imperfections that signal human authorship
  - Slightly unconventional word choices that feel authentic
  - Sentence structures that break "perfect" grammar rules
- **AI-smell words to detect and avoid in generated content:**
  - "delve", "landscape", "leverage", "foster", "paramount"
  - "in today's rapidly evolving...", "it's worth noting that..."
  - Excessive hedging ("arguably", "it could be said")
  - Perfect parallel structures no human writes naturally

**Anti-patterns:** Thesaurus abuse, unnecessary jargon, AI-generated filler

---

### 3. Humor & Wit

**What it captures:** How and when humor is deployed.

**Spectrum anchors:**
- Absent ↔ Pervasive
- Safe ↔ Edgy
- Planned ↔ Spontaneous-feeling

**Types to identify:**
- Self-deprecating ("we built it with duct tape and prayers")
- Cynical/dry ("yes, the AI will definitely solve all your problems")
- Absurdist/exaggerated
- Observational ("you know that moment when...")
- Industry in-jokes

**What to look for:**
- Frequency — every post, occasionally, never?
- Placement — hooks, middle, asides?
- Risk level — could it offend? Does the author care?
- Does humor serve a point or is it decorative?

**Anti-patterns:** Forced humor, emoji-as-humor, "funny" LinkedIn motivational stories

---

### 4. Thought Leadership Stance

**What it captures:** How the author positions their ideas relative to the field.

**Spectrum anchors:**
- Original thinker ↔ Curator/synthesizer
- Contrarian ↔ Consensus-builder
- Bold predictions ↔ Safe observations
- Prescriptive ↔ Descriptive

**What to look for:**
- Do they introduce new frameworks/terms or reference others'?
- How often do they disagree with mainstream views?
- Do they make predictions? How bold?
- "I think X is wrong because Y" vs "here's what I learned from X"
- Do they cite sources or speak from experience?

**Anti-patterns:** Hot takes without substance, agreement-farming, vague "the future is..."

---

### 5. Human Core / Authenticity

**What it captures:** Vulnerability, personal investment, and willingness to show messy reality.

**Spectrum anchors:**
- Polished persona ↔ Raw/unfiltered
- Professional distance ↔ Personal sharing
- Success stories ↔ Failure stories
- Product ↔ Process (showing the work)

**What to look for:**
- Do they share failures, mistakes, uncertainty?
- Personal anecdotes vs abstract principles?
- Work-in-progress or only finished results?
- "I don't know" / "I was wrong" appearances
- Real organizational constraints vs idealized scenarios

**Anti-patterns:** Humblebrags, manufactured vulnerability, "I failed but actually I'm amazing"

---

### 6. Structure & Rhythm

**What it captures:** How posts are built — the architecture of a piece.

**Elements to analyze:**
- **Length:** Short (<100 words), medium (100-300), long (300+)
- **Hook pattern** (first 1-2 lines, before "see more" fold):
  - Question hook / Contrarian statement / Story opening / Bold claim / Relatable scenario
- **Body structure:** Linear narrative, list, problem-then-solution, compare/contrast
- **Paragraph cadence:** Short punchy lines vs flowing paragraphs
- **Formatting:** Line breaks, emojis, bold, bullets, numbered lists
- **CTA pattern:** Ask a question, invite discussion, link to more, none
- **Mobile optimization:** Line break frequency for phone reading

**Anti-patterns:** Wall of text, excessive emoji, clickbait hooks with no payoff

---

### 7. Persuasion Mechanics

**What it captures:** How the author builds conviction and moves the reader.

**Evidence types used:**
- Personal anecdote ("when we did X...")
- Data/numbers ("40% of enterprises...")
- Authority reference ("as [expert] says...")
- Social proof ("600+ attendees")
- Lived experience ("in my 10 years of...")

**Techniques to identify:**
- Objection preemption ("yes, but..." / "I know what you're thinking")
- Reframing ("it's not about X, it's about Y")
- Contrast/juxtaposition ("vendor pitch vs actual constraint")
- Specificity as persuasion (concrete beats abstract)
- Pattern interrupt (breaking expected flow)

**Anti-patterns:** Appeal to authority without substance, empty social proof, manipulation

---

### 8. Topic Framing

**What it captures:** How the author enters and positions a topic.

**Entry angles:**
- **Contrarian:** "Everyone says X, but actually Y"
- **Story-first:** Start with a specific moment/event, then zoom out
- **Question-first:** Pose a question the post will explore
- **News-hook:** React to current event/trend/announcement
- **Experience-first:** "After doing X for Y years..."
- **Problem statement:** "Here's what's broken about..."

**What to look for:**
- Default entry angle (most common across posts)
- Topic selection patterns — what do they write about most?
- How they connect technical topics to business/human impact
- Whether they localize/personalize global trends

**Anti-patterns:** Bandwagon jumping without adding value, topic-of-the-week syndrome

---

## Analysis Output Checklist

For a complete analysis, the agent must produce:
1. **Mode classification** for every post in the corpus (with rationale for non-obvious calls)
2. **Per-dimension assessment** based on authentic voice + thought piece posts only
3. **Evidence** — direct quotes or specific patterns backing each dimension rating
4. **Anti-pattern flags** — any detected anti-patterns, with examples
