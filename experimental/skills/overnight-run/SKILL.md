---
name: overnight-run
description: Run a chief of staff's leads unattended overnight from a one-line ask such as "overnight until <end time>". Settle the night's goals and frame with the owner at kickoff, run one lead per goal inside the boundaries, and hand back a morning report that opens with what waits for the owner.
when_to_use: A chief of staff, working under the chief-of-staff skill, gets an ask to run until a set time without the owner, such as "overnight until <end time>".
---

# Overnight run

A routine for one unattended night, for a chief of staff working under the
`chief-of-staff` skill. It puts that skill's pieces in order and restates none of them:
where a step names a chief-of-staff section, follow that section. Every value (the end
time, the mandate, the boundaries, paths, hosts, tools) is the owner's or the project's to
give. This skill gives none, so a value nobody gave is asked for, never assumed.

## 1. Kickoff, in the evening

The only step that needs the owner. Put everything below to them in one message, then
record their answer.

- **The night's goals.** For each project, draft one or two goals from its board state:
  its open issues, its leads' reports, what waits for the owner. Each goal has:
  - what the lead does, in one line;
  - a test that says by morning whether it is done, something anyone can check (a merged
    PR, a gate's exit, a spec on its issue);
  - your recommendation, run or skip, with its reason.

  The owner strikes or edits them. Silence, meaning no reply by the reply-by time your
  message names (yours to choose, in a timezone it states; the owner's to change), runs the recommended ones. The
  goals that run become the leads' briefs. An approval the board already shows waiting (a
  merge, a spec) is no goal: ask it in its own line, and unanswered it goes on Decide first.
- **The rest of the frame.** Ask the owner to confirm:
  - the end time, with its date and timezone;
  - the mandate: which kinds of decision they delegate to you for the night;
  - the hard boundaries: each project's own list. A project with none gets the question,
    not a list of yours.

  A frame item still unanswered at the reply-by time takes its narrowest reading, and
  that reading goes on Decide first. No mandate delegates nothing: every approval and
  every question waits for Decide first. A project
  with no boundaries stated has its goals held, not run, since its boundaries are its own
  and you can't supply them. An end time without a date or zone is its next occurrence in
  the timezone the project or the owner already records; with neither, no lead starts,
  since a guessed zone can end the night before it begins, and the morning comes at the
  owner's next message. An answer given after the reply-by time replaces its reading from
  then on. State each reading in the kickoff message and in the morning report.
- **Silence chooses work, nothing else.** Silence picks which goals run and approves
  nothing. An approval a goal's work needs (a spec, a merge) comes only from the owner's
  own words: the mandate, or an approval they give during the night, to you or in a
  lead's session. Without it, that approval waits for Decide first. A step that is hard
  to undo waits for the owner whatever the mandate says (chief-of-staff, Authority).
- **Record it.** The goals that run, the end time, the mandate and the boundaries go on
  the board as the night's standing decisions, each the owner's words quoted with its
  citation (chief-of-staff, Authority, Cite it; Handover, Standing decisions). A goal that
  runs by silence is your decision, recorded under yours and citing the kickoff message
  it was not struck from.

## 2. During the run

- Start one lead per goal through the project's start wrapper, on the host the host
  routing table names, within that host's capacity (chief-of-staff, Starting a lead,
  including Host load). Its brief is the goal and its test, saying who set them: an
  owner-edited goal quoted with its citation, a goal that ran by silence marked as your
  own, citing the kickoff message (Starting a lead, Brief). The mandate, the boundaries
  and the end time go in quoted and cited.
- Act on supervisor posts (chief-of-staff, Relaying; What a lead's turn ending means). A
  question the mandate delegates and whose answer is reversible you decide (Authority,
  Delegated decisions). Every other question, approval or step goes on the morning's
  Decide first, and the lead carries on with what does not depend on it.
- Log every decision you take in the project's decision log: what, why, and how to undo
  it.
- Stay inside the boundaries. A step that would cross one is not taken: it goes on Decide
  first.
- At the end time, start nothing new and move to the morning. A lead still running is
  reported with its stage.

## 3. Morning

- Draw the digest of the night's decisions from the project's decision log with the
  project's digest.
- Write the report page where the project keeps it (a file, a published page, a console's
  digest). Its sections, in order:
  1. **Decide first:** each item that waits for the owner, with its options, your
     recommendation and its link.
  2. **Goals:** each goal with its test's result (done, not done, not reached) and its
     link.
  3. **Decisions taken:** the digest, each with how to undo it.
- Archive the finished leads (chief-of-staff, What a lead's turn ending means; Handover,
  Closed) and run the project's hygiene check.
- The night's standing decisions end at the end time: mark them ended on the board
  (Handover), and drop them once the owner has read the report.
