# Sourced by a project's cloud setup script (a Claude cloud environment's setup script), which sets `log` first.
# The cloud proxy answers 403 from api.github.com and refuses mise-versions.jdx.dev and mise.run, while github.com
# release downloads and npm pass: so mise comes from npm, release assets are fetched directly and checked against
# their release's checksums, and mise prefers offline, so it counts a fetched tool as installed instead of asking the
# version list it can't reach. Every step logs its seconds and exit code to "$log"; a failed step logs FAILED and
# the script goes on, since a non-zero exit fails the whole cloud session. ponytail: x86_64 Linux assets only (the
# cloud image's platform); another platform needs its asset names in the caller's fetch lines.

step() {  # step <name> <command...>: run it, log its seconds and exit code
  local s=$(date +%s); "${@:2}" >>"$log.out" 2>&1; local rc=$?
  echo "$1: exit $rc, $(( $(date +%s) - s )) s" >> "$log"
  [ "$rc" = 0 ] || echo "FAILED: $1" >> "$log"
}

# fetch <url> <sha256-list url> <dest> [strip]: a release asset by direct download from github.com, checked
# against its release's checksum list, then installed as the binary <dest>, or a .tar.gz unpacked into <dest>
# less <strip> leading path parts.
fetch() {
  local a="${1##*/}" d; d=$(mktemp -d)
  curl -fsSL -o "$d/$a" "$1" && curl -fsSL -o "$d/sums" "$2" \
    && (cd "$d" && grep " \*\?$a\$" sums | sha256sum -c -) || return 1
  case "$a" in
    *.tar.gz) mkdir -p "$3" && tar -xzf "$d/$a" -C "$3" --strip-components="${4:-0}" ;;
    *) mkdir -p "${3%/*}" && cp "$d/$a" "$3" && chmod 755 "$3" ;;
  esac
}

# setup_mise: mise from npm unless the image has it, trusted configs, and mise's offline preference in its global
# config, so every later mise call in the session, a gate's `mise run` included, uses it
setup_mise() {
  command -v mise >/dev/null || step mise npm install -g -s @jdxcode/mise
  step mise-trust mise trust -q --all
  step mise-offline mise settings set prefer_offline true
}

# version_ok <tool> <wanted>: the tool's first x.y.z in `--version` is at least <wanted> (any version when empty)
version_ok() {
  local have; have=$("$1" --version 2>/dev/null | grep -oE '[0-9]+(\.[0-9]+)+' | head -1)
  [ -n "$have" ] && { [ -z "$2" ] || [ "$(printf '%s\n%s\n' "$2" "$have" | sort -V | head -1)" = "$2" ]; }
}

# setup_requires <skills dir>...: each `metadata.requires` entry (`tool` or `tool>=version`) of every installed
# skill, resolved on PATH at that version, else installed through mise (`mise use -g`); each logs its seconds
setup_requires() {
  local entry tool want
  for entry in $(cat "$@" 2>/dev/null | sed -n 's/^  requires: "\(.*\)"$/\1/p' | tr ' ' '\n' | sort -u); do
    tool=${entry%%>=*} want=""; [ "$tool" = "$entry" ] || want=${entry#*>=}
    version_ok "$tool" "$want" && { echo "requires $entry: present" >> "$log"; continue; }
    step "requires $entry" mise use -g "$tool${want:+@latest}"
    version_ok "$tool" "$want" || { echo "FAILED: requires $entry" >> "$log"; }
  done
}

# setup_uv <releases root> [repo]: uv at the repo's uv.toml required-version (`>=X.Y.Z`) when the image's is older,
# unpacked from astral's release asset into ~/.local/share/uv/<version>, linked into ~/.local/bin
setup_uv() {
  local want a bin="$HOME/.local/bin"
  want=$(sed -n 's/^required-version *= *"[^0-9]*\([0-9][0-9.]*\)".*/\1/p' "${2:-.}/uv.toml" 2>/dev/null | head -1)
  [ -n "$want" ] || return 0
  version_ok uv "$want" && return 0
  a=$1/astral-sh/uv/releases/download/$want/uv-x86_64-unknown-linux-gnu.tar.gz
  step "uv $want" fetch "$a" "$a.sha256" "$HOME/.local/share/uv/$want" 1 \
    && mkdir -p "$bin" && ln -sf "$HOME/.local/share/uv/$want/uv" "$HOME/.local/share/uv/$want/uvx" "$bin/"
}
