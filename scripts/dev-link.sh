#!/usr/bin/env bash
# Live local-dev for this marketplace: point Claude Code's plugin cache at this
# working tree via symlinks, so editing a plugin here + /reload-plugins is enough
# (no GitHub push, no marketplace re-clone, no cache copy).
#
# Re-run this any time `/plugin marketplace update` or a reinstall replaces the
# symlinks with fresh snapshots.
#
# Usage: scripts/dev-link.sh [--unlink]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKET="kzarzycki-agent-skills"            # marketplace name (cache dir under cache/)
CACHE="$HOME/.claude/plugins/cache/$MARKET"

if [[ ! -d "$CACHE" ]]; then
  echo "error: $CACHE not found — install the '$MARKET' marketplace first." >&2
  exit 1
fi

# Each plugin = a top-level dir in the repo with .claude-plugin/plugin.json
for pj in "$REPO"/*/.claude-plugin/plugin.json; do
  [[ -e "$pj" ]] || continue
  plugdir="$(dirname "$(dirname "$pj")")"
  name="$(basename "$plugdir")"
  # reuse the version subdir Claude already installed (e.g. 0.1.0); default if absent
  ver="$(ls "$CACHE/$name" 2>/dev/null | head -1 || true)"; ver="${ver:-0.1.0}"
  target="$CACHE/$name/$ver"

  if [[ "${1:-}" == "--unlink" ]]; then
    if [[ -L "$target" ]]; then
      rm "$target"; cp -r "$plugdir" "$target"
      echo "unlinked $name -> real copy at $target"
    fi
    continue
  fi

  mkdir -p "$CACHE/$name"
  rm -rf "$target"
  ln -s "$plugdir" "$target"
  echo "linked $name/$ver -> $plugdir"
done

[[ "${1:-}" == "--unlink" ]] || echo "done. run /reload-plugins in Claude Code to load live."
