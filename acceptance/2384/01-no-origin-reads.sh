#!/bin/sh
# #2384: no omnigent test reaches a real remote. Every test runs with a `git` shim on PATH that allows only the
# file transport (GIT_ALLOW_PROTOCOL=file), so a call to https, ssh or git:// is refused instead of reaching the
# network, and logs each refused call. Git applies `insteadOf` before the check, so a test that names a GitHub URL
# but maps it to its own bare remote is allowed. The check fails on any logged call, or on a red suite.
set -u
root=$(git rev-parse --show-toplevel)
cd "$root" || exit 1
real=$(command -v git)
shim=$(mktemp -d)
log="$shim/calls.tsv"
: > "$log"
cat > "$shim/git" <<SHIM
#!/bin/sh
err=\$(mktemp)
GIT_ALLOW_PROTOCOL=file "$real" "\$@" 2> "\$err"
rc=\$?
cat "\$err" >&2
if grep -q "transport '.*' not allowed" "\$err"; then
  printf '%s\t%s\n' "\${PYTEST_CURRENT_TEST:-?}" "\$*" >> "$log"
fi
rm -f "\$err"
exit \$rc
SHIM
chmod +x "$shim/git"
PATH="$shim:$PATH" uv run pytest -q -p no:cacheprovider omnigent/tests
rc=$?
calls=$(wc -l < "$log" | tr -d ' ')
echo "git calls to a non-local remote: $calls"
sort "$log" | uniq -c
rm -rf "$shim"
[ "$rc" -eq 0 ] && [ "$calls" -eq 0 ]
