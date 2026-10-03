---
name: demo
description: Record a short video of a change running and post it to its PR, so a reviewer judges a visible change without checking out the branch. Use when a PR changes what a user sees (a command and its output, a page, a screen, a speed-up), on "record a demo", or when the project's instructions or spec ask for one.
---

# Demo

A demo is the change running, recorded at the PR's head and posted on the PR, so a
person can watch it work in a minute instead of checking out the branch. Whether a PR
gets one is the project's call: its agent instructions say when to suggest a demo and
when to record one. Without such a rule, record only when asked.

## Record

When the project's agent docs name a demo command, such as `mise run demo <script>`, use
it. Otherwise pick the recorder for the surface and read its file:

| Surface | Recorder | Read |
|---|---|---|
| CLI or TUI | VHS tape | [recorders/cli.md](recorders/cli.md) |
| Web page | Playwright video | [recorders/browser.md](recorders/browser.md) |
| iOS simulator | `simctl` | [recorders/ios.md](recorders/ios.md) |
| Android emulator or device | `screenrecord` | [recorders/android.md](recorders/android.md) |

A change that spans surfaces gets one short video per surface, posted together.

- Record the real build at the PR's head, so the video proves the change rather than a
  mock. `post_demo.sh` refuses to post from a checkout that is not the PR's head or has
  uncommitted changes; it checks when posting, so record from that same checkout.
- Drive it from a script (a tape, a test, a command list) next to the e2e scenario it
  shows, so a re-recording after a fix is one command and shows a path the tests check.
- Keep secrets off screen (tokens, passwords, `env` output, customer data): anyone who
  can read the PR can download the video, and secret scanning does not read video.
- Produce MP4 with H.264, the one format every browser plays inline.
- Write the video to a temporary folder, never into the repo, since every recording
  would grow every clone.

## Post

```sh
scripts/post_demo.sh [--pr <number>] "<what it shows>" <video.mp4>...
```

`scripts/` is relative to this skill's folder. The script posts one `## Demo` comment
with the videos attached, naming the head commit, and minimizes your earlier `## Demo`
comments as outdated so only the current one is open. The PR defaults to the current
branch's. Then name the demo in the PR body's Evidence.

A project that records often wraps both steps in one task (record to a temporary
folder, then `post_demo.sh`) and names that task in its agent docs.
