#!/bin/bash
# Setup script of the agent-skills-dev Claude cloud environment, whose sessions run the cloud
# worker's light gate, `mise run test`, and its verifier passes (docs/agents/loop.md, Cloud worker).
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
# fetch <url> <sha256-list url> <dest> [strip]: a release asset by direct download from github.com,
# checked against its release's checksum list, then installed as the binary <dest>, or a .tar.gz
# unpacked into <dest> less <strip> leading path parts. mise resolves a github:, aqua: or ubi:
# release, and core:python's build list, through mise-versions.jdx.dev and then api.github.com:
# the proxy refuses the first and answers 403 from the second for repos outside the session, while
# github.com's release downloads pass. A tool at mise's own install path counts as installed, so
# `mise install` and `mise run` skip it.
fetch() {
  local a="${1##*/}" d; d=$(mktemp -d)
  curl -fsSL -o "$d/$a" "$1" && curl -fsSL -o "$d/sums" "$2" \
    && (cd "$d" && grep " \*\?$a\$" sums | sha256sum -c -) || return 1
  case "$a" in
    *.tar.gz) mkdir -p "$3" && tar -xzf "$d/$a" -C "$3" --strip-components="${4:-0}" ;;
    *) install -D -m755 "$d/$a" "$3" ;;
  esac
}
# python_by_uv <version>: core:python's build through uv, whose own list names the
# python-build-standalone release on github.com, linked where mise looks for it
python_by_uv() {
  local p; "$uv" python install "$1" && p=$("$uv" python find --managed-python "$1") \
    && mkdir -p "$mi/python" && ln -sfn "$(dirname "$(dirname "$p")")" "$mi/python/$1"
}
pin() { mise current "$1"; }  # the version mise.toml pins
repo=/home/user/agent-skills
echo "setup start $(date -u +%FT%TZ) user=$(id -un) home=$HOME repo_present=$([ -d "$repo" ] && echo yes || echo no)" >> "$log"
command -v mise >/dev/null || step mise npm install -g -s @jdxcode/mise
step apt sh -c 'apt-get update -qq && apt-get install -y -qq openssh-client'
# the verifier's CLI (docs/agents/loop.md, Cloud verifier), so a pass does not start by installing it
command -v codex >/dev/null || step codex npm install -g -s @openai/codex
cd "$repo" 2>/dev/null || { echo "FAILED: no checkout at $repo" >> "$log"; exit 0; }
step mise-trust mise trust -q --all
# ponytail: x86_64 Linux assets only, the cloud image's platform; another one needs its asset names
mi="$HOME/.local/share/mise/installs" gh=https://github.com
v=$(pin ubi:carvel-dev/vendir); a=$gh/carvel-dev/vendir/releases/download/v$v
step vendir fetch "$a/vendir-linux-amd64" "$a/checksums.txt" "$mi/ubi-carvel-dev-vendir/$v/bin/vendir"
v=$(pin uv); a=$gh/astral-sh/uv/releases/download/$v/uv-x86_64-unknown-linux-gnu.tar.gz
step uv fetch "$a" "$a.sha256" "$mi/uv/$v"
uv="$mi/uv/$v/uv-x86_64-unknown-linux-gnu/uv"
v=$(pin github:microsoft/apm); a=$gh/microsoft/apm/releases/download/v$v/apm-linux-x86_64.tar.gz
step apm fetch "$a" "$a.sha256" "$mi/github-microsoft-apm/$v" 1
step python python_by_uv "$(pin python)"
step mise-install mise install
# the files apm deploys and git ignores (.claude/hooks/...): settings.json's Bash hook fails closed without them
step apm-install mise exec -- apm install --frozen --target claude,codex
step uv-sync mise exec -- uv sync --frozen
missing=""
for tool in mise python uv node vendir apm ssh-keygen codex; do
  mise which "$tool" >/dev/null 2>&1 || command -v "$tool" >/dev/null || missing="$missing $tool"
done
[ -z "$missing" ] || echo "FAILED, missing:$missing" >> "$log"
echo "setup done $(date -u +%FT%TZ), $(( $(date +%s) - t0 )) s total" >> "$log"
exit 0
