#!/usr/bin/env bash
# Post demo videos to a PR as one `## Demo` comment and minimize the earlier ones as outdated.
# gh cannot attach a file to a comment and GitHub has no API for the inline upload, so each
# video becomes an asset of a prerelease (the shared `demos` one, or one per post where releases
# are immutable) and the comment links it.
# Usage: post_demo.sh [--pr <number>] "<what it shows>" <video>...
set -euo pipefail

usage() { echo 'usage: post_demo.sh [--pr <number>] "<what it shows>" <video>...' >&2; exit 2; }

pr=""
if [ "${1:-}" = "--pr" ]; then
  [ $# -ge 2 ] || usage
  [[ $2 =~ ^[0-9]+$ ]] || usage
  pr="$2"
  shift 2
fi
[ $# -ge 2 ] || usage
caption="$1"
shift

for video in "$@"; do
  [ -s "$video" ] || { echo "post_demo: $video is missing or empty" >&2; exit 2; }
done

# With several GitHub remotes and no `gh repo set-default`, gh reads the PR as `upstream`'s: refuse rather than
# post to a repo nobody chose.
repos="$(git remote -v | awk '{print $2}' | sed -E 's#/+$##; s#\.git/*$##' |
  sed -nE 's#^([a-zA-Z][a-zA-Z0-9+.-]*://)?([^@/]*@)?([^/:]+)(:[0-9]+)?[:/]/*([^/]+/[^/]+)$#\3 \5#p' |
  awk 'tolower($1) == "github.com" { print tolower($2) }' | sort -u)"
if [ "$(printf '%s' "$repos" | grep -c .)" -gt 1 ] && ! git config --get-regexp '^remote\..*\.gh-resolved$' >/dev/null; then
  echo "post_demo: this checkout's remotes name $(echo $repos) and gh has no default among them: run gh repo set-default <owner>/<repo>" >&2
  exit 1
fi

pr="${pr:-$(gh pr view --json number --jq .number)}"
head="$(git rev-parse HEAD)"
pr_head="$(gh pr view "$pr" --json headRefOid --jq .headRefOid)"
if [ "$head" != "$pr_head" ]; then
  echo "post_demo: this checkout is at ${head:0:7}, PR #$pr's head is ${pr_head:0:7}; record from a clean checkout of the head" >&2
  exit 3
fi
if ! git diff --quiet HEAD; then
  echo "post_demo: this checkout has uncommitted changes, so the video may not show PR #$pr's head; commit and push them, then record again" >&2
  exit 3
fi

# Read your earlier demos before posting, so the new comment is not among them; a
# reviewer's own `## Demo` comment is left alone.
me="$(gh api user --jq .login)"
old="$(gh api "repos/{owner}/{repo}/issues/$pr/comments" --paginate \
  --jq ".[] | select(.user.login == \"$me\" and (.body | startswith(\"## Demo\"))) | .node_id")"

# Each asset is named after the PR and commit, so a later recording never replaces the video
# an earlier comment links; on the shared `demos` release a re-recording of the same commit
# replaces that commit's video.
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
names=()
i=0
for video in "$@"; do
  i=$((i + 1))
  name="pr$pr-${head:0:7}-$i.mp4"
  names+=("$name")
  cp "$video" "$staging/$name"
done
files=("${names[@]/#/$staging/}")

# An immutable release refuses uploads once published, so such a repo gets one prerelease per
# post, its videos attached by the same `release create`. A 404 or any failure reads as off.
immutable="$(gh api "repos/{owner}/{repo}/immutable-releases" --jq .enabled 2>/dev/null || echo false)"
if [ "$immutable" = true ]; then
  tag="demo-pr$pr-${head:0:7}-$(date +%Y%m%d%H%M%S)"
  gh release create "$tag" "${files[@]}" --target "$head" --prerelease --title "Demo: PR #$pr, ${head:0:7}" \
    --notes "Demo videos linked from pull request #$pr." >/dev/null
else
  tag=demos
  gh release view demos >/dev/null 2>&1 ||
    gh release create demos --prerelease --title Demos \
      --notes "Demo videos linked from pull request comments." >/dev/null
  for file in "${files[@]}"; do gh release upload demos "$file" --clobber; done
fi
download="$(gh repo view --json url --jq .url)/releases/download/$tag"
links=""
for name in "${names[@]}"; do
  links+="
- [$name]($download/$name)"
done

gh pr comment "$pr" --body "## Demo

$caption, on ${head:0:7}.
$links"

for id in $old; do
  # shellcheck disable=SC2016  # $id is a GraphQL variable, not a shell one.
  gh api graphql -f query='mutation($id: ID!) { minimizeComment(input: {subjectId: $id, classifier: OUTDATED}) { clientMutationId } }' \
    -f id="$id" >/dev/null || echo "post_demo: posted, but could not minimize $id" >&2
done
