"""cloud-setup.sh installs what apm deploys, since settings.json's Bash hook fails closed without it (#1444)."""

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETUP = (ROOT / ".claude" / "cloud-setup.sh").read_text()
LIB_PATH = ROOT / "loop" / "skills" / "engineering-loop" / "scripts" / "cloud-setup-lib.sh"
LIB = LIB_PATH.read_text() if LIB_PATH.exists() else ""  # absent before #962: each test then fails on its own
PINS = tomllib.loads((ROOT / "mise.toml").read_text())["tools"]


def test_apm_install_follows_mise_install() -> None:
    assert "step mise-install mise install" in LIB  # setup_pins runs it
    assert SETUP.index('setup_pins "$repo"') < SETUP.index(
        "step apm-install mise exec -- apm install --frozen"
    )


def release_assets(pbs: str) -> dict[str, dict[str, bytes]]:
    """Each fetched pin's release asset, laid out as the real x86_64 Linux one: vendir a bare binary, uv and apm in a
    wrapper directory, python under python/bin. Keys are URL paths below the release root, values the archive's files."""
    v = {tool.split("/")[-1]: pin for tool, pin in PINS.items()}

    def tool(name: str) -> bytes:
        return f'#!/bin/sh\necho {name} "$@"\n'.encode()

    return {
        f"carvel-dev/vendir/releases/download/v{v['vendir']}/vendir-linux-amd64": {
            "": tool("vendir")
        },
        f"astral-sh/uv/releases/download/{v['uv']}/uv-x86_64-unknown-linux-gnu.tar.gz": {
            "uv-x86_64-unknown-linux-gnu/uv": tool("uv"),
            "uv-x86_64-unknown-linux-gnu/uvx": tool("uvx"),
        },
        f"microsoft/apm/releases/download/v{v['apm']}/apm-linux-x86_64.tar.gz": {
            "apm-linux-x86_64/apm": tool("apm")
        },
        f"astral-sh/python-build-standalone/releases/download/{pbs}/"
        f"cpython-{v['python']}+{pbs}-x86_64-unknown-linux-gnu-install_only.tar.gz": {
            f"python/bin/python{'.'.join(v['python'].split('.')[:2])}": tool("python"),
            "python/bin/python3": b"@python3.14",
            "python/bin/python": b"@python3.14",
        },
    }


def publish(root: Path, assets: dict[str, dict[str, bytes]]) -> None:
    """Write each asset under root with the checksum list its release ships beside it."""
    lists: dict[Path, list[str]] = {}
    for url, files in assets.items():
        path = root / url
        path.parent.mkdir(parents=True, exist_ok=True)
        if "" in files:
            path.write_bytes(files[""])
        else:
            with tarfile.open(path, "w:gz") as tar:
                for name, data in files.items():
                    info = tarfile.TarInfo(name)
                    if data.startswith(b"@"):
                        info.type, info.linkname = tarfile.SYMTYPE, data[1:].decode()
                        tar.addfile(info)
                    else:
                        info.size, info.mode = len(data), 0o755
                        tar.addfile(info, io.BytesIO(data))
        line = f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        if path.name.endswith(".tar.gz") and "python-build-standalone" not in url:
            path.with_name(path.name + ".sha256").write_text(line + "\n")
        else:  # one list for the release: vendir's checksums.txt, python-build-standalone's SHA256SUMS
            lists.setdefault(
                path.parent / ("checksums.txt" if "vendir" in url else "SHA256SUMS"), []
            ).append(line)
    for path, lines in lists.items():
        path.write_text("\n".join(lines) + "\n")


GH_QUOTA = ROOT / "github" / "skills" / "gh-quota" / "scripts"


def gh_quota_pinned(setup: str, files: Path) -> str:
    """cloud-setup.sh with its gh-quota sums swapped for the sums of `files`, the same two files, so a test serves
    this checkout's gh-quota in place of the pinned commit's, which a shallow clone may not hold."""
    for name in ("gh", "gh_quota.py"):
        digest = hashlib.sha256((files / name).read_bytes()).hexdigest()
        setup, n = re.subn(
            rf"^[0-9a-f]{{64}}  {re.escape(name)}$", f"{digest}  {name}", setup, flags=re.MULTILINE
        )
        assert n == 1, name
    return setup


def run_setup(
    tmp_path: Path,
    corrupt: str = "",
    gh_quota_sum: str = "",
    repo_files: dict[str, str] | None = None,
    fakes: dict[str, str] | None = None,
    with_mise: bool = True,
    extra_assets: dict[str, dict[str, bytes]] | None = None,
    corrupt_hits: int = 1,
) -> tuple[str, Path, dict[str, str]]:
    """Run cloud-setup.sh against file:// release assets, in an empty mise home and a checkout pinning every tool
    but node (the one mise fetches itself), with mise's network refused and no other copy of a pinned tool on PATH. `corrupt` names an asset
    whose checksum list is wrong; `gh_quota_sum` a gh-quota file whose pinned sum is wrong."""
    mise = shutil.which("mise")
    assert mise, "mise runs this suite"
    mise_dir = [str(Path(mise).parent)] if with_mise else []
    home, repo, releases, bin_ = (tmp_path / d for d in ("home", "repo", "releases", "bin"))
    for d in (home, repo, bin_):
        d.mkdir()
    publish(releases, release_assets(re.search(r"pbs=(\d+)", SETUP)[1]) | (extra_assets or {}))
    if corrupt:  # the asset's line in whichever list its release ships: <asset>.sha256, checksums.txt, SHA256SUMS
        hit = 0
        for sums in (
            f for f in releases.rglob("*") if f.name.endswith(("sha256", "SUMS", "checksums.txt"))
        ):
            lines = sums.read_text().splitlines(keepends=True)
            bad = [
                "0" * 64 + line[64:] if line.split()[-1].startswith(corrupt) else line
                for line in lines
            ]
            hit += bad != lines
            sums.write_text("".join(bad))
        assert hit == corrupt_hits, (corrupt, hit)
    pins = {tool: pin for tool, pin in PINS.items() if tool != "node"}
    (repo / "mise.toml").write_text(
        "[tools]\n" + "".join(f'"{t}" = "{p}"\n' for t, p in pins.items())
    )
    for name, body in {  # outside this test: the image's packages
        **dict.fromkeys(("apt-get", "codex", "ssh-keygen", "gh"), "#!/bin/sh\n"),
        **(fakes or {}),
    }.items():
        (bin_ / name).write_text(body)
        (bin_ / name).chmod(0o755)
    for name, body in (repo_files or {}).items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(body)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith(("MISE_", "XDG_", "NO_PROXY"))
    }
    # a proxy that refuses every connection, as the cloud's refuses mise's lookups, so mise downloads nothing itself;
    # the fetches read file:// assets, which take no proxy
    env |= {
        name: "http://127.0.0.1:9"
        for name in (
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "ALL_PROXY",
            "https_proxy",
            "http_proxy",
            "all_proxy",
        )
    }
    env |= {
        "HOME": str(home),
        "PATH": os.pathsep.join([str(bin_), *mise_dir, "/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
        "CLOUD_SETUP_LOG": str(tmp_path / "setup.log"),
        "CLOUD_SETUP_REPO": str(repo),
        "CLOUD_SETUP_RELEASES": releases.as_uri(),
        "CLOUD_SETUP_GH_QUOTA": GH_QUOTA.as_uri(),
        "CLOUD_SETUP_LIB": str(LIB_PATH),
    }
    env["CLOUD_SETUP_IMAGE_PATH"] = str(
        bin_
    )  # the script's own image directories hold this VM's mise and npm
    setup = gh_quota_pinned(SETUP, GH_QUOTA)
    if gh_quota_sum:
        setup = re.sub(
            rf"^[0-9a-f]{{64}}(?=  {re.escape(gh_quota_sum)}$)", "0" * 64, setup, flags=re.MULTILINE
        )
    (tmp_path / "cloud-setup.sh").write_text(setup)
    subprocess.run(
        ["bash", str(tmp_path / "cloud-setup.sh")],
        env=env,
        check=True,
        capture_output=True,
        timeout=60,  # without prefer_offline mise retries the refused proxy for minutes
    )
    return (tmp_path / "setup.log").read_text(), repo, env


def test_every_pinned_tool_but_node_is_installed_where_mise_finds_it(tmp_path: Path) -> None:
    """The fetched pins are what mise resolves offline, so a task runs them and no other copy (#1536)."""
    log, repo, env = run_setup(tmp_path)
    assert "FAILED" not in log.replace("FAILED, missing: node", ""), (
        log + (tmp_path / "setup.log.out").read_text()
    )
    for name in ("vendir", "uv", "apm", "python"):
        found = subprocess.run(
            ["mise", "which", name], cwd=repo, env=env, text=True, capture_output=True, check=False
        )
        assert found.returncode == 0, (name, found.stderr)
        assert found.stdout.startswith(
            str(tmp_path / "home" / ".local" / "share" / "mise" / "installs")
        ), found.stdout


@pytest.mark.parametrize(
    ("tool", "asset", "installs"),
    [
        ("vendir", "vendir-", "ubi-carvel-dev-vendir"),
        ("uv", "uv-", "uv"),
        ("apm", "apm-", "github-microsoft-apm"),
        ("python", "cpython-", "python"),
    ],
)
def test_a_checksum_mismatch_installs_nothing(
    tmp_path: Path, tool: str, asset: str, installs: str
) -> None:
    """Each release's own checksum list is checked: a wrong line for one asset leaves only that tool missing."""
    log, _repo, _env = run_setup(tmp_path, corrupt=asset)
    assert f"FAILED: {tool}\n" in log, log
    # node, which this checkout leaves unpinned, is the one other tool missing
    assert sorted(log.split("FAILED, missing:")[1].split("\n")[0].split()) == sorted(
        [tool, "node"]
    ), log
    assert not (tmp_path / "home" / ".local" / "share" / "mise" / "installs" / installs).exists()


def test_mise_prefers_offline_before_it_installs() -> None:
    """Offline, mise counts the fetched tools as installed; online it exits 1 and drops them from a task's PATH (#1536)."""
    assert (
        "step mise-offline mise settings set prefer_offline true" in LIB
    )  # the library's setup_mise
    assert SETUP.index('setup_mise "$repo"') < SETUP.index(
        'setup_pins "$repo"'
    )  # which runs mise install


def test_gh_quota_shim_goes_ahead_of_the_images_gh(tmp_path: Path) -> None:
    """Setup puts gh-quota's shim in ~/.local/bin, ahead of the image's gh on a session's PATH, so each later
    session logs its gh calls with no step of its own, and keeps gh_quota.py beside it for `counts`."""
    log, _repo, _env = run_setup(tmp_path)
    home = tmp_path / "home"
    assert "gh-quota: exit 0" in log, log + (tmp_path / "setup.log.out").read_text()
    assert (home / ".local" / "bin" / "gh").read_bytes() == (GH_QUOTA / "gh").read_bytes()
    assert (home / ".local" / "share" / "gh-quota" / "gh_quota.py").is_file()
    assert SETUP.index("step gh-quota ") < SETUP.index('cd "$repo"')  # it needs no checkout


@pytest.mark.parametrize("name", ["gh", "gh_quota.py"])
def test_a_gh_quota_sum_mismatch_installs_no_shim(tmp_path: Path, name: str) -> None:
    """A file that is not the pinned one is never run: the step fails, setup goes on, and the image's gh stays."""
    log, _repo, _env = run_setup(tmp_path, gh_quota_sum=name)
    assert "FAILED: gh-quota\n" in log, log
    assert "setup done" in log
    assert not (tmp_path / "home" / ".local" / "bin" / "gh").exists()
    assert not (tmp_path / "home" / ".local" / "share" / "gh-quota").exists()


def test_the_gh_quota_pin_names_a_commit_and_both_sums() -> None:
    """The step reads the pack at one commit, never a branch, and checks each of the two files it runs."""
    assert re.search(r"^ghq=[0-9a-f]{40}$", SETUP, re.MULTILINE)
    assert "/$ghq/github/skills/gh-quota/scripts" in SETUP
    for name in ("gh", "gh_quota.py"):
        assert re.search(rf"^[0-9a-f]{{64}}  {re.escape(name)}$", SETUP, re.MULTILINE), name


def test_the_setup_script_sources_the_library_and_defines_no_step_or_fetch_of_its_own() -> None:
    assert re.search(r'^\. "\$lib"$', SETUP, re.MULTILINE)
    assert not re.search(r"^(step|fetch)\(\)", SETUP, re.MULTILINE)
    assert re.search(r"^(step|fetch)\(\)", LIB, re.MULTILINE)


def test_mise_comes_from_npm(tmp_path: Path) -> None:
    """With no mise on PATH, mise is installed through npm and set to prefer offline, with no request to the hosts the
    proxy refuses (the probe in #962: mise.run, mise-versions.jdx.dev and api.github.com fail, npm passes)."""
    home, calls = tmp_path / "home", tmp_path / "mise.calls"
    fake_mise = f'#!/bin/sh\necho "$@" >> {calls}\n'
    fake_npm = (  # `npm install -g -s @jdxcode/mise` leaves a mise on PATH
        f'#!/bin/sh\necho npm "$@" >> {tmp_path / "npm.calls"}\n'
        f"printf '%s' '{fake_mise}' > {tmp_path / 'bin'}/mise && chmod 755 {tmp_path / 'bin'}/mise\n"
    )
    curl = f'#!/bin/sh\necho "$@" >> {tmp_path / "curl.calls"}\nexec /usr/bin/curl "$@"\n'
    log, _repo, _env = run_setup(tmp_path, with_mise=False, fakes={"npm": fake_npm, "curl": curl})
    assert "mise: exit 0" in log, log + (tmp_path / "setup.log.out").read_text()
    assert "npm install -g -s @jdxcode/mise" in (tmp_path / "npm.calls").read_text()
    assert "settings set prefer_offline true" in calls.read_text()
    requested = (tmp_path / "curl.calls").read_text() if (tmp_path / "curl.calls").exists() else ""
    for host in ("mise.run", "mise-versions.jdx.dev", "api.github.com"):
        assert host not in requested, (host, requested)
    assert home.is_dir()


def fake_installing_mise(tmp_path: Path, versions: dict[str, str]) -> str:
    """A mise whose `use -g <tool>` puts <tool> in its shims dir, as the real one does, printing its version for a
    tool named in `versions` and failing for the rest; `which` finds a shim first; the rest is the real mise's."""
    real = shutil.which("mise")
    shims = tmp_path / "home" / ".local" / "share" / "mise" / "shims"
    cases = "".join(
        f"    {tool}) mkdir -p {shims}; printf '#!/bin/sh\\necho {tool} version {ver}\\n' > {shims}/{tool};"
        f" chmod 755 {shims}/{tool}; exit 0;;\n"
        for tool, ver in versions.items()
    )
    return (
        "#!/bin/sh\n"
        f'case "$1" in\n  use) case "$3" in\n{cases}    *) exit 1;;\n  esac;;\n'
        f'  which) [ -x {shims}/"$2" ] && echo {shims}/"$2" || exec {real} "$@";;\n  *) exec {real} "$@";;\nesac\n'
    )


def skill(name: str, requires: str) -> dict[str, str]:
    return {
        f".claude/skills/{name}/SKILL.md": f'---\nname: {name}\nmetadata:\n  requires: "{requires}"\n---\nbody\n'
    }


def test_requires_resolve_and_log(tmp_path: Path) -> None:
    """Skills declaring `gh>=2.99.0 uv vhs`: gh is too old, so mise installs it; uv is the checkout's pin, already
    there; vhs is one mise can't install. The log has a line per tool with its seconds, FAILED for the one missing."""
    old_gh = "#!/bin/sh\necho gh version 2.50.0 '(2025-01-01)'\n"
    fake = fake_installing_mise(tmp_path, {"gh": "2.99.1"})
    log, _repo, env = run_setup(
        tmp_path,
        repo_files={
            **skill("a", "gh>=2.99.0 uv"),
            **skill("b", "vhs uv"),
        },  # uv is the checkout's pin, fetched
        fakes={"mise": fake, "gh": old_gh},
    )
    for tool in ("gh", "uv", "vhs"):
        assert re.search(
            rf"^require {tool}: \w+, \d+ s$|^require {tool}: exit 1, \d+ s$", log, re.MULTILINE
        ), log
    assert re.search(r"^require gh: installed, \d+ s$", log, re.MULTILINE), log
    assert re.search(r"^require uv: present, 0 s$", log, re.MULTILINE), log
    assert "FAILED: require vhs\n" in log
    assert "FAILED: require gh" not in log and "FAILED: require uv" not in log
    shims = tmp_path / "home" / ".local" / "share" / "mise" / "shims"
    assert (shims / "gh").is_file() and not (shims / "vhs").exists()
    assert log.count("require uv:") == 1  # a tool two skills name is checked once
    for tool in ("gh", "uv"):  # what resolves after setup, as a later session finds it
        found = subprocess.run(
            ["sh", "-c", f"command -v {tool}"],
            env={**env, "PATH": f"{shims}{os.pathsep}{env['PATH']}"},
            text=True,
            capture_output=True,
            check=False,
        )
        assert found.returncode == 0, tool


def test_a_present_tool_is_not_installed_again(tmp_path: Path) -> None:
    fake = fake_installing_mise(tmp_path, {"gh": "2.99.1"})
    gh_ok = "#!/bin/sh\necho gh version 2.99.0 '(2025-01-01)'\n"
    log, _repo, _env = run_setup(
        tmp_path, repo_files=skill("a", "gh>=2.99.0"), fakes={"mise": fake, "gh": gh_ok}
    )
    assert re.search(r"^require gh: present, 0 s$", log, re.MULTILINE), log
    assert not (tmp_path / "home" / ".local" / "share" / "mise" / "shims" / "gh").exists()


UV_SUMS = "astral-sh/uv/releases/download/0.13.4/uv-x86_64-unknown-linux-gnu.tar.gz"


def uv_case(tmp_path: Path, corrupt: str = "") -> tuple[str, subprocess.CompletedProcess[str]]:
    old_uv = "#!/bin/sh\necho uv 0.11.32\n"
    new_uv = b"#!/bin/sh\necho uv 0.13.4\n"
    log, _repo, env = run_setup(
        tmp_path,
        corrupt=corrupt,
        corrupt_hits=2,  # the pinned uv's release and the required one's both start `uv-`
        repo_files={"uv.toml": 'required-version = ">=0.13.4"\n'},
        fakes={"uv": old_uv},
        extra_assets={UV_SUMS: {"uv-x86_64-unknown-linux-gnu/uv": new_uv}},
    )
    # a later session's PATH, as the setup script exports it: ~/.local/bin ahead of the image's tools
    path = os.pathsep.join([str(tmp_path / "home" / ".local" / "bin"), env["PATH"]])
    return log, subprocess.run(
        ["sh", "-c", "uv --version"],
        env={**env, "PATH": path},
        text=True,
        capture_output=True,
        check=False,
    )


def test_uv_brought_to_required_version(tmp_path: Path) -> None:
    """An image uv older than uv.toml's required-version ends at or above it, checked against the release's sha256;
    a wrong sum leaves the old uv and logs FAILED."""
    (tmp_path / "ok").mkdir()
    log, ran = uv_case(tmp_path / "ok")
    assert "uv-required: exit 0" in log, log
    assert ran.stdout.strip() == "uv 0.13.4", (ran, log)


def test_a_wrong_uv_sum_leaves_the_old_uv(tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    log, ran = uv_case(tmp_path / "bad", corrupt="uv-x86_64")
    assert "FAILED: uv-required\n" in log, log
    assert ran.stdout.strip() == "uv 0.11.32", (ran, log)
