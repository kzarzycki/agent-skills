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
pin() { mise current "$1"; }  # the version mise.toml pins
repo=${CLOUD_SETUP_REPO:-/home/user/agent-skills}
# the library is in the checkout, so a missing checkout ends setup before its first step
. "${CLOUD_SETUP_LIB:-$repo/loop/skills/engineering-loop/scripts/cloud-setup-lib.sh}" \
  || { echo "FAILED: no cloud-setup-lib.sh in $repo" >> "$log"; exit 0; }
echo "setup start $(date -u +%FT%TZ) user=$(id -un) home=$HOME repo_present=$([ -d "$repo" ] && echo yes || echo no)" >> "$log"
step apt sh -c 'apt-get update -qq && apt-get install -y -qq openssh-client'
# the verifier's CLI (docs/agents/loop.md, Cloud verifier), so a pass does not start by installing it
command -v codex >/dev/null || step codex npm install -g -s @openai/codex
# gh-quota's logging shim (github/skills/gh-quota) ahead of the image's gh, so every later session logs its gh calls
# by caller with no step of its own: the skill's two files from the public pack at a pinned commit (the github-v0.1.1
# release; move the commit and both sums with a new one), checked against their sums and kept in ~/.local/share/gh-quota,
# where `gh_quota.py counts` runs, then `install` copies the shim to ~/.local/bin, which a session's PATH puts ahead
# of /usr/local/bin's gh. $HOME is in the environment's snapshot, as mise's installs are.
ghq=c08d02c488c50fc5aa6dce31b59471e7cb41a6ae
ghq_src=${CLOUD_SETUP_GH_QUOTA:-https://raw.githubusercontent.com/kzarzycki/agent-skills/$ghq/github/skills/gh-quota/scripts}
gh_quota() {
  local d="$HOME/.local/share/gh-quota" t f; t=$(mktemp -d)
  for f in gh gh_quota.py; do curl -fsSL -o "$t/$f" "$ghq_src/$f" || return 1; done
  (cd "$t" && sha256sum -c -) <<'EOF' || return 1
31c9eeae51cf1fc772ccdea078384e6219d2d67f608e86d771a7de8130ff2a65  gh
2f2b0d4b5adb627ef3087765e76cbe411cd19ffdb6e099a76dd8af2d8ae16417  gh_quota.py
EOF
  mkdir -p "$d" && cp "$t/gh" "$t/gh_quota.py" "$d/" && python3 "$d/gh_quota.py" install
}
step gh-quota gh_quota
cd "$repo" 2>/dev/null || { echo "FAILED: no checkout at $repo" >> "$log"; exit 0; }
setup_mise
setup_uv "${CLOUD_SETUP_RELEASES:-https://github.com}"
setup_requires .claude/skills/*/SKILL.md .agents/skills/*/SKILL.md
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
