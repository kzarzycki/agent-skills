# Cloud setup library: sourced by a project's cloud setup script (this repo's .claude/cloud-setup.sh is one), so every
# project's VM gets what the installed skills need from one code path (#962). Source it with bash, after setting
# `log` (the file each step's seconds and exit code go to; its output goes to $log.out) and `PATH`. Every function
# logs a failure as `FAILED: <name>` and returns 0: a non-zero exit fails the whole cloud session.
#
# What the cloud proxy lets through (measured on a cloud session): github.com release downloads and registry.npmjs.org
# pass; api.github.com answers 403 and mise.run and mise-versions.jdx.dev refuse the connection. So mise comes from npm,
# release assets are downloaded directly and checked against the release's checksum list, and mise runs offline.
# ponytail: x86_64 Linux assets only, the cloud image's platform; another one needs its asset names.

step() {  # step <name> <command...>: run it, log its seconds and exit code
  local s rc; s=$(date +%s); "${@:2}" >>"$log.out" 2>&1; rc=$?
  echo "$1: exit $rc, $(( $(date +%s) - s )) s" >> "$log"
  [ "$rc" = 0 ] || echo "FAILED: $1" >> "$log"
  return 0
}

# fetch <url> <sha256-list url> <dest> [strip]: a release asset by direct download from github.com, checked against
# its release's checksum list, then installed as the binary <dest>, or a .tar.gz unpacked into <dest> less <strip>
# leading path parts. mise resolves a github:, aqua: or ubi: release, and core:python's build list, through
# mise-versions.jdx.dev and then api.github.com, which the proxy refuses: so a tool mise can't look up is fetched.
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
export PATH="$HOME/.local/share/mise/shims:$PATH"

# setup_mise [checkout]: mise from npm when the image has none, trusted in the checkout, and offline. A tool at mise's
# own install path counts as installed once mise prefers offline: without it `mise install` exits 1 on the version
# list it cannot fetch and `mise run` leaves that tool off the task's PATH. The setting is global, so every later mise
# call in the session, the gate's `mise run` included, uses it.
setup_mise() {
  command -v mise >/dev/null || step mise npm install -g -s @jdxcode/mise
  step mise-trust sh -c 'cd "$1" 2>/dev/null && mise trust -q --all' _ "${1:-.}"
  step mise-offline mise settings set prefer_offline true
}

# version_ok <have> <want>: have >= want, comparing dotted numbers
version_ok() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }

# resolve <tool>: the path where mise or PATH finds it, empty when neither does
resolve() { mise which "$1" 2>/dev/null || command -v "$1" || true; }

# satisfies <tool> <minimum>: the tool resolves, and at `minimum` (when there is one) or newer
satisfies() {
  local bin have; bin=$(resolve "$1"); [ -n "$bin" ] || return 1
  [ -z "$2" ] && return 0
  have=$("$bin" --version 2>&1 | grep -oE '[0-9]+(\.[0-9]+)+' | head -1)
  [ -n "$have" ] && version_ok "$have" "$2"
}

# setup_requires <checkout>: each `metadata.requires` entry (`tool` or `tool>=version`) of each skill installed in the
# checkout is skipped when it already resolves at that version, else installed with mise; the log has one line per tool
# with its seconds, and `FAILED: require <tool>` when it still doesn't resolve. The entries' format is the one
# tests/test_skill_requires.py checks.
setup_requires() {
  local entry tool want s id
  cd "$1" 2>/dev/null || return 0
  for entry in $(sed -n 's/^  requires: "\(.*\)"$/\1/p' .claude/skills/*/SKILL.md .agents/skills/*/SKILL.md \
      */skills/*/SKILL.md 2>/dev/null | tr ' ' '\n' | sort -u); do
    tool=${entry%%>=*}; want=""; [ "$tool" = "$entry" ] || want=${entry#*>=}
    s=$(date +%s)
    if satisfies "$tool" "$want"; then
      echo "require $tool: present, 0 s" >> "$log"; continue
    fi
    id=$tool; [ "$tool" != python3 ] || id=python  # the mise tool's name
    mise use -g "$id" >>"$log.out" 2>&1
    if satisfies "$tool" "$want"; then
      echo "require $tool: installed, $(( $(date +%s) - s )) s" >> "$log"
    else
      echo "require $tool: exit 1, $(( $(date +%s) - s )) s" >> "$log"
      echo "FAILED: require $tool" >> "$log"
    fi
  done
}

# uv_required [checkout]: uv at or above the `required-version` of the checkout's uv.toml, else the release's uv at the
# pinned version (when mise.toml pins one that satisfies it) or at the required minimum, checked against the release's
# sha256. It goes where mise finds it when mise.toml pins uv, else into ~/.local/bin. A wrong sum leaves the old uv.
uv_required() {
  local want v a dest
  want=$(sed -n 's/^required-version *= *"[>=]*\([0-9][0-9.]*\)".*/\1/p' "${1:-.}/uv.toml" 2>/dev/null | head -1)
  [ -n "$want" ] || return 0
  satisfies uv "$want" && return 0
  v=$(cd "${1:-.}" && pin uv 2>/dev/null); dest="$HOME/.local/bin"
  if [ -n "$v" ] && version_ok "$v" "$want"; then dest="$HOME/.local/share/mise/installs/uv/$v"; else v=$want; fi
  a=${CLOUD_SETUP_RELEASES:-https://github.com}/astral-sh/uv/releases/download/$v/uv-x86_64-unknown-linux-gnu.tar.gz
  step uv-required fetch "$a" "$a.sha256" "$dest" 1
}

# setup_pins <checkout>: bring each tool the repo pins up to that version. The project defines `pinned_fetches` (its
# `step <name> fetch ...` lines) for the tools mise can't look up here, uv to its uv.toml's required-version follows,
# then `mise install` takes what is left from mise.toml.
setup_pins() {
  cd "$1" 2>/dev/null || return 0
  if declare -F pinned_fetches >/dev/null; then pinned_fetches; fi
  uv_required "$1"
  step mise-install mise install
}
