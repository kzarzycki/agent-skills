#!/bin/sh
# #2384: no supervisor or start test reaches the checkout's origin. Every omnigent test runs with a `git` shim on
# PATH that logs each network call (ls-remote, fetch, pull, push) aimed at a remote that is not a local path; the
# check fails on any such line, or on a red suite. A test's own bare remote is a local path, so it is never logged.
set -u
root=$(git rev-parse --show-toplevel)
cd "$root" || exit 1
shim=$(mktemp -d)
log="$shim/calls.tsv"
: > "$log"
cat > "$shim/git" <<SHIM
#!/bin/sh
dir=.
[ "\$1" = "-C" ] && dir=\$2
case " \$* " in
  *" ls-remote "*|*" fetch "*|*" pull "*|*" push "*)
    url=\$("$(command -v git)" -C "\$dir" config --get remote.origin.url 2>/dev/null)
    case "\$url \$*" in
      *://*|*git@*) printf '%s\t%s\t%s\n' "\${PYTEST_CURRENT_TEST:-?}" "\$url" "\$*" >> "$log" ;;
    esac ;;
esac
exec "$(command -v git)" "\$@"
SHIM
chmod +x "$shim/git"
PATH="$shim:$PATH" uv run pytest -q -p no:cacheprovider omnigent/tests
rc=$?
echo "network git calls to a non-local remote: $(wc -l < "$log")"
cut -f1 "$log" | sort | uniq -c
calls=$(wc -l < "$log")
rm -rf "$shim"
[ "$rc" -eq 0 ] && [ "$calls" -eq 0 ]
