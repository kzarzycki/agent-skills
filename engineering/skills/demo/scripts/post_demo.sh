#!/usr/bin/env bash
# Post demo videos to a PR as one `## Demo` comment and minimize the earlier ones as outdated.
# Usage: post_demo.sh [--pr <number>] "<what it shows>" <video>...
set -euo pipefail

usage() { echo 'usage: post_demo.sh [--pr <number>] "<what it shows>" <video>...' >&2; exit 2; }

pr=""
if [ "${1:-}" = "--pr" ]; then
  [ $# -ge 2 ] || usage
  pr="$2"
  shift 2
fi
[ $# -ge 2 ] || usage
caption="$1"
shift

attach=()
for video in "$@"; do
  [ -s "$video" ] || { echo "post_demo: $video is missing or empty" >&2; exit 2; }
  # gh refuses alt text on a video, so attach the bare path.
  attach+=(--attach "$video")
done

pr="${pr:-$(gh pr view --json number --jq .number)}"
head="$(git rev-parse HEAD)"
pr_head="$(gh pr view "$pr" --json headRefOid --jq .headRefOid)"
if [ "$head" != "$pr_head" ]; then
  echo "post_demo: this checkout is at ${head:0:7}, PR #$pr's head is ${pr_head:0:7}; push or check out the head, then record again" >&2
  exit 3
fi

# Read the earlier demos before posting, so the new comment is not among them.
old="$(gh api "repos/{owner}/{repo}/issues/$pr/comments" --paginate \
  --jq '.[] | select(.body | startswith("## Demo")) | .node_id')"

gh pr comment "$pr" --body "## Demo

$caption, on ${head:0:7}." "${attach[@]}"

for id in $old; do
  # shellcheck disable=SC2016  # $id is a GraphQL variable, not a shell one.
  gh api graphql -f query='mutation($id: ID!) { minimizeComment(input: {subjectId: $id, classifier: OUTDATED}) { clientMutationId } }' \
    -f id="$id" >/dev/null
done
