#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: macOS only; run this helper on the machine with the .app bundle" >&2
  exit 2
fi

if [[ $# -ne 1 ]]; then
  echo "usage: macos-app-provenance.sh /path/to/App.app" >&2
  exit 2
fi

app_path="$1"
if [[ ! -d "$app_path" || "${app_path##*.}" != "app" ]]; then
  echo "error: $app_path is not a .app bundle" >&2
  exit 2
fi

plist="$app_path/Contents/Info.plist"

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().rstrip("\n")))'
}

plist_value() {
  local key="$1"
  if [[ -f "$plist" ]] && command -v /usr/libexec/PlistBuddy >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Print :$key" "$plist" 2>/dev/null || true
  fi
}

codesign_out="$(codesign -dv --verbose=4 "$app_path" 2>&1 || true)"
spctl_out="$(spctl --assess --type execute --verbose=4 "$app_path" 2>&1 || true)"
entitlements_out="$(codesign -d --entitlements :- "$app_path" 2>/dev/null || true)"
quarantine_out="$(xattr -p com.apple.quarantine "$app_path" 2>/dev/null || true)"

bundle_id="$(plist_value CFBundleIdentifier)"
short_version="$(plist_value CFBundleShortVersionString)"
build_version="$(plist_value CFBundleVersion)"
team_id="$(printf '%s\n' "$codesign_out" | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
notarization="$(printf '%s\n' "$spctl_out" | awk '/source=Notarized Developer ID/{print "notarized"; exit}')"
if [[ -z "$notarization" ]]; then
  notarization="unknown-or-not-notarized"
fi

cat <<JSON
{
  "app_path": $(printf '%s' "$app_path" | json_escape),
  "bundle_id": $(printf '%s' "$bundle_id" | json_escape),
  "short_version": $(printf '%s' "$short_version" | json_escape),
  "build_version": $(printf '%s' "$build_version" | json_escape),
  "team_id": $(printf '%s' "$team_id" | json_escape),
  "notarization": $(printf '%s' "$notarization" | json_escape),
  "quarantine": $(printf '%s' "$quarantine_out" | json_escape),
  "codesign": $(printf '%s' "$codesign_out" | json_escape),
  "spctl": $(printf '%s' "$spctl_out" | json_escape),
  "entitlements": $(printf '%s' "$entitlements_out" | json_escape)
}
JSON
