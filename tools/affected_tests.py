"""The tests a change touches, for the Mergify batch (`mise run test-batch`): prints one pytest target per line.

When it can't tell exactly, it runs the narrowest set it can still name, never nothing for a product change (#2217;
the engineering loop's rule, "A check runs only if it can fail because of the change"). The changed files come from
`git diff` against the base (origin/main, or argv[1]); a base git can't resolve (the all-zeros SHA of a new branch)
falls back to the merge base with origin's default branch, and with no merge base either the run fails. A build input
(BUILD_INPUTS: pyproject.toml, uv.lock, mise.toml, the root conftest.py), which every test reads, runs the whole suite.
A nested conftest.py runs the test files under its directory (#1460). A changed test file runs. A changed file a test
reads by path (any file, `.md` included) runs the tests whose source names it by its path, or by its parent
directory and its file name, quoted (#2216). A changed script runs the tests that executed the lines it changed, read
from the test map the nightly builds (below), else every test file that names its stem (any other non-markdown file:
its file name); a file no test names runs its package's tests, else the tests of its nearest directory that has some
(home_tests). A skill's prose, which the repo-wide checks `tests/test_skill_*.py` read, runs those. Zero tests run only
when every changed path is non-product (NON_PRODUCT) and no test reads it, and the run says `0 selected: non-product`.
In the merge queue (`GITHUB_HEAD_REF` under `mergify/merge-queue/`, or `GATE_IN_QUEUE=1`) a build input selects the whole
suite only under `select.build_inputs_in_queue: full` in docs/agents/gatekeeper.md; under `floor`, the default there,
it selects the other changed files' tests, and for a changed `uv.lock` the tests that import a package whose version
changed (#2445). The nightly and a push to main, which touch a build input, run the whole suite after the merge.
A selection of over half the test files runs as picked (#1872): only the nightly runs the whole suite.

The test map is `.test-map/` (env `TEST_MAP`): `coverage`, the nightly suite's coverage data with one context per test
(`pytest --cov-context=test`), and `sha`, the commit it ran on. A changed line of a script is looked up at its old
position (the diff runs from that commit), and the tests that executed it run, one node id each (a file when the id
holds a space, since the gate splits this output on whitespace, or names a test the file no longer has). The name match
is the fallback for a script the map does not hold or that changed on main since it, a map whose commit is missing or
data is unreadable, and a changed line that any import or subprocess ran, since no test is named for that run. A
line beside an inserted whole new undecorated function or class is not changed, so its import run is no reason;
beside any other insertion (a decorator, a constant, an import) it counts as changed, since that code runs at import. It also
adds, beside the map's tests, every test file that names the script and changed on main since the map, and of those
files the tests the nightly skipped (a skip leaves no context): by node id from the map's `skipped` list, else, for a
map without one, every such file that can skip. A line no test ran selects nothing: no test depends on it.
"""

from __future__ import annotations

import fnmatch
import importlib.metadata
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ALL = [
    "tests",
    "engineering/tests",
    "gatekeeper/tests",
    "loop/tests",
    "github/tests",
    "chief-of-staff/tests",
    "omnigent/tests",
]
# files every test reads (the runner's config, the lock, the toolchain pins, the root conftest): a change runs the suite
# (gatekeeper.md's `select.build_inputs` is this list, which tests/test_own_loop_settings.py holds: the selector's own code
# and the pack's `affected_tests` are in it, since a change to the selector can't be judged by the selector it changes)
BUILD_INPUTS = (
    "pyproject.toml",
    "uv.lock",
    "mise.toml",
    "conftest.py",
    "tools/affected_tests.py",
    "gatekeeper/skills/gatekeeper/scripts/gatekeeper.py",
)
# paths no product test can fail on, unless a test reads one by path: design notes, the repo's own top-level prose,
# changelog entries, an agent's config and vendored skills, the pack's own pin (fnmatch: `*` crosses `/`)
NON_PRODUCT = (
    "docs/*",
    "*/changelog.d/*",
    "*CHANGELOG.md",
    ".agents/*",
    ".claude/*",
    "apm.yml",
    "apm.lock.yaml",
)
MAP = Path(os.environ.get("TEST_MAP", ".test-map"))
SKIPS = re.compile(r"needs_tool|skipif|pytest\.skip|importorskip")
# repo-wide sweeps that name no script, so the name match never picks them: every skill folder's files, run on any
# change (#2372). test_one_package_per_skill_name.py rejects a file a batch adds to a skill folder.
SWEEPS = ("tests/test_one_package_per_skill_name.py",)
CHEAP = sorted([*(str(p) for p in Path("tests").glob("test_skill_*.py")), *SWEEPS])
# docs a test holds byte for byte against a copy, which no name match finds: a change to one runs that test
DOC_TESTS = {
    "loop/skills/engineering-loop/": "tests/test_old_paths.py",
    "engineering/skills/engineering-loop/": "tests/test_old_paths.py",
}


def changed(base: str) -> list[str] | None:
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.split() if done.returncode == 0 else None


def queue_build_inputs() -> str:
    """`floor` or `full`: what a build input selects here. Outside the merge queue it is `full`, as ever; inside it is
    gatekeeper.md's `select.build_inputs_in_queue`, `floor` when unset."""
    head = os.environ.get("GITHUB_HEAD_REF", "")
    if not (head.startswith("mergify/merge-queue/") or os.environ.get("GATE_IN_QUEUE") == "1"):
        return "full"
    try:
        text = Path("docs/agents/gatekeeper.md").read_text()
    except OSError:
        return "floor"
    found = re.search(r"^[ \t]+build_inputs_in_queue:[ \t]*(floor|full)\b", text, re.MULTILINE)
    return found[1] if found else "floor"


def locked(base: str | None, ref: str) -> dict[str, str]:
    """The package versions of `uv.lock` at `ref` (`HEAD` or the base), empty when there is none."""
    done = subprocess.run(
        ["git", "show", f"{ref}:uv.lock"], capture_output=True, text=True, check=False
    )
    if done.returncode:
        return {}
    try:
        data = tomllib.loads(done.stdout)
    except tomllib.TOMLDecodeError:
        return {}
    return {p["name"]: p.get("version", "") for p in data.get("package", []) if "name" in p}


def import_names(package: str) -> set[str]:
    """The names a package is imported by, from the top-level modules its installed distribution provides (`pyyaml` is
    imported as `yaml`), read from the distributions' files, not a `top_level.txt` a wheel may lack. Empty when no
    installed distribution provides one: the name is not known."""
    wanted = re.sub(r"[-_.]+", "-", package).lower()
    return {
        module
        for module, dists in importlib.metadata.packages_distributions().items()
        if any(re.sub(r"[-_.]+", "-", dist).lower() == wanted for dist in dists)
    }


def lock_floor(base: str | None, tests: list[Path], sources: dict[Path, str]) -> set[str] | None:
    """The test files that import a package `uv.lock` adds, removes or moves to another version since `base`; None
    when a moved package maps to no import name (not installed here), since the floor can't tell what imports it."""
    before, after = locked(base, base or "HEAD"), locked(base, "HEAD")
    said = sorted(
        name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
    )
    picked: set[str] = set()
    for package in said:
        if not (names := import_names(package)):
            say(f"uv.lock: {package} maps to no import name: the whole suite")
            return None
        for name in names:
            use = re.compile(rf"^\s*(?:import|from)\s+{re.escape(name)}\b", re.MULTILINE)
            picked |= {str(t) for t in tests if use.search(sources[t])}
    say(f"uv.lock moved {len(said)} packages: {len(picked)} test files import them")
    return picked


def default_base() -> str | None:
    """The merge base of HEAD with origin's default branch (origin/HEAD, else origin/main), None when git has none."""
    head = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    branch = head.stdout.strip() if head.returncode == 0 and head.stdout.strip() else "origin/main"
    done = subprocess.run(
        ["git", "merge-base", branch, "HEAD"], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def resolve(base: str) -> tuple[str, list[str]] | None:
    """The base the selection diffs against and the files changed since it: `base`, else (a base git can't resolve,
    such as a new branch's all-zeros SHA) the merge base with origin's default branch; None when neither diffs."""
    if (files := changed(base)) is not None:
        return base, files
    if (fallback := default_base()) is None or (files := changed(fallback)) is None:
        return None
    say(
        f"the base {base} is no commit here: the merge base {fallback[:12]} with the default branch"
    )
    return fallback, files


QUOTE = "[\"'/]"


def reads(path: str, text: str) -> bool:
    """Whether a test's source names `path` as a file it reads: its whole path, or its parent directory and its file
    name each as a quoted string or a path segment (`LOOP / "verifier.md"` beside `"engineering-loop"`)."""
    if path in text:
        return True
    parent, name = Path(path).parent.name, Path(path).name
    if not parent:
        return False
    return all(re.search(f"{QUOTE}{re.escape(word)}{QUOTE}", text) for word in (name, parent))


def home_tests(path: str, tests: list[Path]) -> tuple[str, list[str]]:
    """The tests of the package or directory nearest `path` that has any: walking up from its directory, the first of
    `<dir>/tests` (a suite root in ALL) or `<dir>` itself (under a suite root) that holds a test file, the repo root's
    suite last. The fallback for a file no test names, since a change nothing names is not one nothing depends on."""
    parts = Path(path).parts[:-1]
    for depth in range(len(parts), -1, -1):
        here = "/".join(parts[:depth])
        for root in (f"{here}/tests" if here else "tests", here):
            under = root and any(root == r or root.startswith(f"{r}/") for r in ALL)
            if under and (found := [str(t) for t in tests if t.as_posix().startswith(f"{root}/")]):
                return root, found
    return "", []


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? [^\n]*\n((?:[-+ \\][^\n]*\n?)*)", re.MULTILINE)
NEW_BLOCK = re.compile(r"(?:async\s+def|def|class)\s")


def new_block(added: list[str]) -> bool:
    """Whether inserted lines are only whole new undecorated `def`s or `class`es (blank lines between): code no import
    runs but its definition, so no existing test runs it until a changed caller does."""
    lines = [line for line in added if line.strip()]
    if not lines or not NEW_BLOCK.match(lines[0].lstrip()):
        return False
    indent = len(lines[0]) - len(lines[0].lstrip())
    for line in lines:
        depth = len(line) - len(line.lstrip())
        if depth < indent or (depth == indent and not NEW_BLOCK.match(line.lstrip())):
            return False  # a decorator, a constant, a statement at the block's own level
    return True


def old_lines(sha: str, path: str) -> tuple[set[int], set[int]]:
    """The lines of `path` at `sha` that the diff to HEAD changes, and the lines around each insertion of whole new
    undecorated functions or classes (new_block), which stand for that code without being changed themselves. Any
    other insertion counts the lines around it as changed: a decorator or a module-level line runs at import."""
    diff = subprocess.run(
        ["git", "diff", "-U0", "--no-renames", sha, "HEAD", "--", path],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    changed: set[int] = set()
    around: set[int] = set()
    for start, count, body in HUNK.findall(diff):
        first, n = int(start), int(count or 1)
        if n:
            changed.update(range(first, first + n))
        else:
            added = [line[1:] for line in body.splitlines() if line.startswith("+")]
            (around if new_block(added) else changed).update((first, first + 1))
    return changed, around - changed


def executed_by(path: str, sha: str, data) -> set[str] | None:
    """The test node ids that ran the lines of `path` changed since `sha`; None when the name match must decide."""
    ran = data.contexts_by_lineno(path) if path in data.measured_files() else None
    if ran is None:
        return None
    ids: set[str] = set()
    changed, around = old_lines(sha, path)
    for line in changed | around:
        # import or a subprocess ran a changed line: no test is named for that run. A line beside a new function or
        # class (old_lines) is not changed, so the import that ran it (the `def` line above, say) says nothing of
        # that code: only the tests that ran it count.
        if line in changed and "" in ran.get(line, ()):
            return None
        ids |= {c.split("|")[0] for c in ran.get(line, ()) if c}
    return ids


def load_map():
    """The map's commit and coverage data, or None when there is none or its commit is gone (the data is None for a map
    that measures no file)."""
    try:
        from coverage import CoverageData
        from coverage.exceptions import CoverageException
    except ImportError:
        return None
    try:
        sha = (MAP / "sha").read_text().strip()
        known = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, check=False
        )
        data = CoverageData(basename=str(MAP / "coverage"))
        data.read()
        measured = (
            data.measured_files()
        )  # opens the data now: a truncated file raises here, not mid-selection
        # a map that measures no file is (sha, None): targets() says it is empty, which no map at all is not (#1400)
        return (sha, data if measured else None) if known.returncode == 0 else None
    except OSError, CoverageException:
        return None


def skipped() -> set[str] | None:
    """The node ids the map's run skipped (`skipped` beside it, from tools/test_map_plugin.py), or None for a map with no
    such list, whose skips are then guessed from the test files' text (SKIPS)."""
    try:
        return set((MAP / "skipped").read_text().split())
    except OSError:
        return None


def moved_since(sha: str, base: str | None) -> set[str]:
    """The files that changed between the map's commit and the PR's base: the map has not seen them."""
    if base is None:
        return set()
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", sha, base],
        capture_output=True,
        text=True,
        check=False,
    )
    return set(done.stdout.split())


def node_files(ids: set[str]) -> set[str]:
    """Node ids as pytest targets: the id itself when it has no whitespace and its test still exists; a parametrized id
    with whitespace (the gate splits on it) as its test function, every parameter of it; else its file."""
    out = set()
    for node in ids:
        file, _, name = node.partition("::")
        if not Path(file).exists():
            continue
        function = re.split(r"[\[]", name)[0]  # `test_x`, or `TestK::test_x` in a class
        alive = f"def {function.rsplit('::', 1)[-1]}(" in Path(file).read_text(errors="ignore")
        if alive and not re.search(r"\s", node):
            out.add(node)
        elif alive and not re.search(r"\s", function):
            out.add(f"{file}::{function}")
        else:
            out.add(file)
    return out


PACKAGE_CODE = re.compile(r"^([^/]+)/(?:[^/]+/)*(?:scripts|src)/[^/]+\.py$")


def package_tests(path: str, tests: list[Path]) -> list[str]:
    """Every test file of the package whose `scripts/` or `src/` holds `path`, else none: the fallback when no test
    is found for a changed script, since a change nothing names or ran is not one nothing depends on (#2157)."""
    m = PACKAGE_CODE.match(path)
    if not m or f"{m[1]}/tests" not in ALL:
        return []
    return [str(t) for t in tests if t.as_posix().startswith(f"{m[1]}/tests/")]


def say(line: str) -> None:
    """One line on stderr naming the rule that picked a target, so a slow run's log shows why it ran what it did."""
    print(f"affected-tests: {line}", file=sys.stderr)


def non_product(path: str) -> bool:
    """Whether `path` is one no product test can fail on (NON_PRODUCT, or a top-level `.md`), unless a test reads it."""
    return ("/" not in path and path.endswith(".md")) or any(
        fnmatch.fnmatch(path, glob) for glob in NON_PRODUCT
    )


def targets(
    files: list[str], base: str | None = None, build_inputs: str | None = None
) -> list[str]:
    """The pytest targets for the change `files` since `base`: the narrowest set the rules above can name.
    `build_inputs` is `floor` or `full` (queue_build_inputs when None): under `full` a build input selects the whole
    suite; under `floor` it adds nothing, but a changed `uv.lock` adds the tests importing a moved package."""
    mode = build_inputs or queue_build_inputs()
    inputs = [f for f in files if f in BUILD_INPUTS]
    if inputs and mode == "full":
        say(f"{inputs[0]}: a build input, which every test reads: the whole suite")
        return list(ALL)
    lock_moved = "uv.lock" in inputs
    files = [f for f in files if f not in inputs]
    tests = [
        p for r in ALL for p in sorted(Path(r).rglob("test_*.py")) if "/e2e/" not in p.as_posix()
    ]
    sources = {t: t.read_text(errors="ignore") for t in tests}
    picked: set[str] = set()
    product = False  # a changed path some test can fail on: only a change with none selects zero
    mapped = load_map()
    if (
        mapped and mapped[1] is None
    ):  # a map that holds nothing decides nothing: say so, once (#1400)
        say(
            f"map is empty (map of {mapped[0][:12]} measures no file): a script runs every test that names it"
        )
        mapped = None
    else:
        say(
            f"map of {mapped[0][:12]}"
            if mapped
            else f"no map at {MAP}: a script runs every test that names it"
        )
    if inputs:
        product = True
        if lock_moved:
            if (found := lock_floor(base, tests, sources)) is None:
                return list(ALL)
            picked |= found
        say(f"{inputs[0]}: a build input: the floor, the whole suite runs after the merge")
    ran: set[str] = set()
    moved = moved_since(mapped[0], base) if mapped else set()
    skips = skipped() if mapped else None
    for f in files:
        path = Path(f)
        if by_path := {str(t) for t, text in sources.items() if reads(f, text)}:
            say(f"{f}: {len(by_path)} test files read it by path")
            picked |= by_path
            product = True
        if (
            path.name.startswith("test_")
            and path.suffix == ".py"
            and path.exists()
            and f.startswith(tuple(f"{r}/" for r in ALL))
        ):  # a test file under a suite root; `tools/test_map_plugin.py` is a plugin, which the name match covers
            picked.add(f)
            product = True
            say(f"{f}: a changed test")
        elif path.name == "conftest.py":  # a nested one: the root's is a build input
            here = path.parent.as_posix()
            under = [str(t) for t in tests if t.as_posix().startswith(f"{here}/")]
            say(f"{f}: test setup: the {len(under)} test files under {here}")
            picked.update(under)
            product = True
        elif non_product(f):
            named = (
                set()
                if path.suffix == ".md"
                else {str(t) for t, text in sources.items() if path.name in text}
            )
            picked |= named
            product = product or bool(named)
            if not (named or by_path):
                say(f"{f}: non-product, and no test reads it")
        elif path.suffix == ".md":
            product = True
            say(f"{f}: a skill's prose: the repo-wide checks read it")
            for prefix, test in DOC_TESTS.items():
                if f.startswith(prefix):
                    picked.add(test)
                    say(f"{f}: {test} holds a copy of it")
        else:
            product = True
            by_run = executed_by(f, *mapped) if mapped and path.suffix == ".py" else None
            needle = path.stem if path.suffix == ".py" else path.name
            named = {t: text for t, text in sources.items() if needle in text}
            if by_run is not None and f not in moved:
                say(f"{f}: {len(by_run)} tests from the map")
                ran |= by_run
                # the name match stays the floor where the map is blind: a test the map has not seen (new or
                # changed on main since it) and a test the nightly may skip (it has no context)
                floor = {
                    str(t)
                    for t, text in named.items()
                    if str(t) in moved or (skips is None and SKIPS.search(text))
                }
                picked.update(floor)
                skipped_here = set()
                if skips is not None:  # the tests of these files the map's run skipped, by node id
                    skipped_here = {n for n in skips if n.split("::")[0] in {str(t) for t in named}}
                    ran |= skipped_here
                if (
                    not by_run
                    and not floor
                    and not skipped_here
                    and (pkg := package_tests(f, tests))
                ):
                    say(f"{f}: no test ran it: the package's {len(pkg)} test files")
                    picked.update(pkg)
                continue
            if mapped and path.suffix == ".py":
                why = (
                    "changed on main since the map"
                    if f in moved
                    else "an import ran its change"
                    if f in mapped[1].measured_files()
                    else f"map has no entry for {f}"
                )
                say(f"{f}: {len(named)} test files name it ({why})")
            else:
                say(f"{f}: {len(named)} test files name it")
            picked.update(str(t) for t in named)
            if not named and not by_path:
                home, found = home_tests(f, tests)
                say(f"{f}: no test names it: the {len(found)} test files under {home or 'nothing'}")
                picked.update(found)
    if not product:
        say("0 selected: non-product")
        return []
    picked.update(CHEAP)
    picked.update(n for n in node_files(ran) if n.split("::")[0] not in picked)
    return sorted(picked)


if __name__ == "__main__":
    given = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    if (found := resolve(given)) is None:
        say(
            f"no diff against {given} nor a merge base with the default branch: fetch origin deeper"
        )
        sys.exit(1)
    print("\n".join(targets(found[1], found[0])))
