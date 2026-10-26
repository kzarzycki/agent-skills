#!/bin/bash
# Setup script of the agent-skills-dev Claude cloud environment, whose sessions run the cloud
# worker's light gate, `mise run test` (docs/agents/loop.md, Cloud worker).
# It installs what the cloud image lacks and pre-warms the repo's pinned tools and package
# caches in the session's checkout, so the environment's snapshot (taken when setup ends within
# about 5 minutes) carries them into later sessions. Each step's seconds and exit code go to
# /tmp/cloud-setup.log, its output to /tmp/cloud-setup.log.out; a failed step is logged as
# FAILED and the script still exits 0, since a non-zero exit fails the whole cloud session.
set -u
log=/tmp/cloud-setup.log
export PATH="$HOME/.local/bin:/opt/node22/bin:/usr/local/bin:$PATH"
t0=$(date +%s)
step() {  # step <name> <command...>: run it, log its seconds and exit code
  local s=$(date +%s); "${@:2}" >>"$log.out" 2>&1; local rc=$?
  echo "$1: exit $rc, $(( $(date +%s) - s )) s" >> "$log"
  [ "$rc" = 0 ] || echo "FAILED: $1" >> "$log"
}
# fetch <url> <sha256-list url> <asset> <dest>: a release asset by direct download, checked
# against the release's checksum list. The proxy refuses api.github.com for repos outside the
# session, which mise's ubi:/github: backends need to resolve a release.
fetch() {
  local d="/tmp/fetch-$3"; mkdir -p "$d"
  curl -fsSL -o "$d/$3" "$1" && curl -fsSL -o "$d/sums" "$2" \
    && (cd "$d" && grep " \*\?$3\$" sums | sha256sum -c -) && install -D -m755 "$d/$3" "$4"
}
repo=/home/user/agent-skills
echo "setup start $(date -u +%FT%TZ) user=$(id -un) home=$HOME repo_present=$([ -d "$repo" ] && echo yes || echo no)" >> "$log"
command -v mise >/dev/null || step mise npm install -g -s @jdxcode/mise
step apt sh -c 'apt-get update -qq && apt-get install -y -qq openssh-client'
cd "$repo" 2>/dev/null || { echo "FAILED: no checkout at $repo" >> "$log"; exit 0; }
step mise-trust mise trust -q --all
v=0.46.0; step vendir fetch https://github.com/carvel-dev/vendir/releases/download/v$v/vendir-linux-amd64 \
  https://github.com/carvel-dev/vendir/releases/download/v$v/checksums.txt vendir-linux-amd64 \
  "$HOME/.local/share/mise/installs/ubi-carvel-dev-vendir/$v/bin/vendir"
step mise-install mise install
step uv-sync mise exec -- uv sync --frozen
missing=""
for tool in mise python uv node vendir apm ssh-keygen; do
  mise which "$tool" >/dev/null 2>&1 || command -v "$tool" >/dev/null || missing="$missing $tool"
done
[ -z "$missing" ] || echo "FAILED, missing:$missing" >> "$log"
echo "setup done $(date -u +%FT%TZ), $(( $(date +%s) - t0 )) s total" >> "$log"
exit 0
