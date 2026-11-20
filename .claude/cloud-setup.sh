#!/bin/bash
# Setup script of the agent-skills-dev Claude cloud environment, whose sessions run the cloud
# worker's light gate, `mise run test`, and its verifier passes (docs/agents/loop.md, Cloud worker).
# It installs what the cloud image lacks and pre-warms the repo's pinned tools and package
# caches in the session's checkout, so the environment's snapshot (taken when setup ends within
# about 5 minutes) carries them into later sessions. Each step's seconds and exit code go to
# /tmp/cloud-setup.log, its output to /tmp/cloud-setup.log.out; a failed step is logged as
# FAILED and the script still exits 0, since a non-zero exit fails the whole cloud session.
set -u
# tests/test_cloud_setup.py runs it against its own release assets, checkout and log
log=${CLOUD_SETUP_LOG:-/tmp/cloud-setup.log}
export PATH="$HOME/.local/bin:/opt/node22/bin:/usr/local/bin:$PATH"
t0=$(date +%s)
step() {  # step <name> <command...>: run it, log its seconds and exit code
  local s=$(date +%s); "${@:2}" >>"$log.out" 2>&1; local rc=$?
  echo "$1: exit $rc, $(( $(date +%s) - s )) s" >> "$log"
  [ "$rc" = 0 ] || echo "FAILED: $1" >> "$log"
}
# fetch <url> <sha256-list url> <dest> [strip]: a release asset by direct download from github.com,
# checked against its release's checksum list, then installed as the binary <dest>, or a .tar.gz
# unpacked into <dest> less <strip> leading path parts. mise resolves a github:, aqua: or ubi:
# release, and core:python's build list, through mise-versions.jdx.dev and then api.github.com:
# the proxy refuses the first and answers 403 from the second for repos outside the session, while
# github.com's release downloads pass. A tool at mise's own install path counts as installed once
# mise prefers offline (the mise-offline step): without it, `mise install` exits 1 on the version
# list it cannot fetch and `mise run` leaves that tool off the task's PATH.
fetch() {
  local a="${1##*/}" d; d=$(mktemp -d)
  curl -fsSL -o "$d/$a" "$1" && curl -fsSL -o "$d/sums" "$2" \
    && (cd "$d" && grep " \*\?$a\$" sums | sha256sum -c -) || return 1
  case "$a" in
    *.tar.gz) mkdir -p "$3" && tar -xzf "$d/$a" -C "$3" --strip-components="${4:-0}" ;;
    *) mkdir -p "${3%/*}" && cp "$d/$a" "$3" && chmod 755 "$3" ;;
  esac
}
pin() { mise current "$1"; }  # the version mise.toml pins
repo=${CLOUD_SETUP_REPO:-/home/user/agent-skills}
echo "setup start $(date -u +%FT%TZ) user=$(id -un) home=$HOME repo_present=$([ -d "$repo" ] && echo yes || echo no)" >> "$log"
command -v mise >/dev/null || step mise npm install -g -s @jdxcode/mise
step apt sh -c 'apt-get update -qq && apt-get install -y -qq openssh-client'
# the verifier's CLI (docs/agents/loop.md, Cloud verifier), so a pass does not start by installing it
command -v codex >/dev/null || step codex npm install -g -s @openai/codex
cd "$repo" 2>/dev/null || { echo "FAILED: no checkout at $repo" >> "$log"; exit 0; }
step mise-trust mise trust -q --all
# global config, so every later mise call in the session, the gate's `mise run` included, uses it
step mise-offline mise settings set prefer_offline true
# ponytail: x86_64 Linux assets only, the cloud image's platform; another one needs its asset names
mi="$HOME/.local/share/mise/installs" gh=${CLOUD_SETUP_RELEASES:-https://github.com}
v=$(pin ubi:carvel-dev/vendir); a=$gh/carvel-dev/vendir/releases/download/v$v
step vendir fetch "$a/vendir-linux-amd64" "$a/checksums.txt" "$mi/ubi-carvel-dev-vendir/$v/vendir"
v=$(pin uv); a=$gh/astral-sh/uv/releases/download/$v/uv-x86_64-unknown-linux-gnu.tar.gz
step uv fetch "$a" "$a.sha256" "$mi/uv/$v" 1
v=$(pin github:microsoft/apm); a=$gh/microsoft/apm/releases/download/v$v/apm-linux-x86_64.tar.gz
step apm fetch "$a" "$a.sha256" "$mi/github-microsoft-apm/$v" 1
# core:python's build from python-build-standalone, which keeps only each minor's newest patch in a
# release, so the release that holds the pinned one is named here and moves with the pin
v=$(pin python) pbs=20260804
a=$gh/astral-sh/python-build-standalone/releases/download/$pbs
step python fetch "$a/cpython-$v+$pbs-x86_64-unknown-linux-gnu-install_only.tar.gz" "$a/SHA256SUMS" "$mi/python/$v" 1
step mise-install mise install
# the files apm deploys and git ignores (.claude/hooks/...): settings.json's Bash hook fails closed without them
step apm-install mise exec -- apm install --frozen --target claude,codex
step uv-sync mise exec -- uv sync --frozen
missing=""
# a pinned tool counts only where mise resolves it, since another copy on PATH (the image's uv) hides
# a fetch mise can't find, and a task then runs that copy instead of the pin
for tool in python uv node vendir apm; do mise which "$tool" >/dev/null 2>&1 || missing="$missing $tool"; done
for tool in mise ssh-keygen codex; do command -v "$tool" >/dev/null || missing="$missing $tool"; done
[ -z "$missing" ] || echo "FAILED, missing:$missing" >> "$log"
echo "setup done $(date -u +%FT%TZ), $(( $(date +%s) - t0 )) s total" >> "$log"
exit 0
