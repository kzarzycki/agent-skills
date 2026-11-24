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
LIB = ROOT / "loop" / "skills" / "engineering-loop" / "scripts" / "cloud-setup-lib.sh"
SETUP = (ROOT / ".claude" / "cloud-setup.sh").read_text()
PINS = tomllib.loads((ROOT / "mise.toml").read_text())["tools"]


def test_apm_install_follows_mise_install() -> None:
    assert SETUP.index("step mise-install ") < SETUP.index(
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
    tmp_path: Path, corrupt: str = "", gh_quota_sum: str = ""
) -> tuple[str, Path, dict[str, str]]:
    """Run cloud-setup.sh against file:// release assets, in an empty mise home and a checkout pinning every tool
    but node (the one mise fetches itself), with mise's network refused and no other copy of a pinned tool on PATH. `corrupt` names an asset
    whose checksum list is wrong; `gh_quota_sum` a gh-quota file whose pinned sum is wrong."""
    mise = shutil.which("mise")
    assert mise, "mise runs this suite"
    home, repo, releases, bin_ = (tmp_path / d for d in ("home", "repo", "releases", "bin"))
    for d in (home, repo, bin_):
        d.mkdir()
    publish(releases, release_assets(re.search(r"pbs=(\d+)", SETUP)[1]))
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
        assert hit == 1, (corrupt, hit)
    pins = {tool: pin for tool, pin in PINS.items() if tool != "node"}
    (repo / "mise.toml").write_text(
        "[tools]\n" + "".join(f'"{t}" = "{p}"\n' for t, p in pins.items())
    )
    for fake in ("apt-get", "codex", "ssh-keygen", "gh"):  # outside this test: the image's packages
        (bin_ / fake).write_text("#!/bin/sh\n")
        (bin_ / fake).chmod(0o755)
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
        "PATH": os.pathsep.join(
            [str(bin_), str(Path(mise).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        ),
        "CLOUD_SETUP_LOG": str(tmp_path / "setup.log"),
        "CLOUD_SETUP_REPO": str(repo),
        "CLOUD_SETUP_LIB": str(LIB),
        "CLOUD_SETUP_RELEASES": releases.as_uri(),
        "CLOUD_SETUP_GH_QUOTA": GH_QUOTA.as_uri(),
    }
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
    assert "step mise-offline mise settings set prefer_offline true" in LIB.read_text()
    assert SETUP.index("setup_mise\n") < SETUP.index("step mise-install ")


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


def lib(tmp_path: Path, script: str, tools: dict[str, str]) -> tuple[str, Path]:
    """Run `script` with the library sourced, on a PATH of only the stubs in `tools` (name -> shell body) and the
    system's; curl is a stub that records its URL and fails, as the proxy does for mise.run. Returns the setup log
    and the stub call log."""
    bin_, home = tmp_path / "bin", tmp_path / "home"
    bin_.mkdir()
    home.mkdir()
    calls = tmp_path / "calls"
    for name, body in {"curl": "exit 22", **tools}.items():
        (bin_ / name).write_text(f'#!/bin/sh\necho "{name} $*" >> {calls}\n{body}\n')
        (bin_ / name).chmod(0o755)
    log = tmp_path / "setup.log"
    env = {"HOME": str(home), "PATH": f"{home}/.local/bin:{bin_}:/usr/bin:/bin:/sbin"}
    subprocess.run(
        ["bash", "-c", f'log={log}; . {LIB}; cd {tmp_path}; {script}'],
        env=env, check=True, capture_output=True, timeout=60,
    )
    return log.read_text(), calls


def test_mise_comes_from_npm(tmp_path: Path) -> None:
    """Without mise, setup_mise installs it with npm and sets prefer_offline: mise.run, the version list and the API are not asked."""
    npm = f'printf "#!/bin/sh\\necho mise \\"\\$@\\" >> {tmp_path}/calls\\n" > {tmp_path}/bin/mise; chmod +x {tmp_path}/bin/mise'
    log, calls = lib(tmp_path, "setup_mise", {"npm": npm})
    seen = calls.read_text()
    assert "npm install -g -s @jdxcode/mise" in seen and "mise settings set prefer_offline true" in seen
    for host in ("mise.run", "mise-versions.jdx.dev", "api.github.com", "curl"):
        assert host not in seen, seen
    assert "FAILED" not in log, log


def test_requires_resolve_and_log(tmp_path: Path) -> None:
    """Each installed skill's requires entry is resolved or installed, with its seconds logged, FAILED where mise can't."""
    skill = tmp_path / "skills" / "a"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text('---\nname: a\nmetadata:\n  requires: "gh>=2.99.0 uv vhs"\n---\n')
    new_gh = f'printf "#!/bin/sh\\necho gh version 3.0.0\\n" > {tmp_path}/bin/gh'
    tools = {
        "gh": "echo gh version 2.0.0",  # older than the skill wants
        "uv": "echo uv 0.13.4",
        "mise": f'[ "$3" = vhs ] && exit 1; {new_gh}; exit 0',
    }
    log, _ = lib(tmp_path, "setup_requires skills/*/SKILL.md", tools)
    assert re.search(r"^requires gh>=2.99.0: exit 0, \d+ s$", log, re.MULTILINE), log
    assert "requires uv: present" in log
    assert re.search(r"^requires vhs: exit 1, \d+ s$", log, re.MULTILINE), log
    assert "FAILED: requires vhs\n" in log and "FAILED: requires gh" not in log


@pytest.mark.parametrize("good", [True, False])
def test_uv_brought_to_required_version(tmp_path: Path, good: bool) -> None:
    """An image's uv older than uv.toml's required-version is replaced by the release's, checked against its sha256;
    a wrong sum leaves the old uv and logs FAILED."""
    (tmp_path / "uv.toml").write_text('required-version = ">=0.13.4"\n')
    releases = tmp_path / "releases"
    asset = "astral-sh/uv/releases/download/0.13.4/uv-x86_64-unknown-linux-gnu.tar.gz"
    publish(releases, {asset: {"uv-x86_64-unknown-linux-gnu/uv": b"#!/bin/sh\necho uv 0.13.4\n"}})
    if not good:
        sums = releases / (asset + ".sha256")
        sums.write_text("0" * 64 + sums.read_text()[64:])
    # the real curl: the assets are file:// URLs
    log, _ = lib(
        tmp_path,
        f"setup_uv {releases.as_uri()}; uv --version >> {tmp_path}/out",
        {"uv": "echo uv 0.11.0", "curl": f'exec {shutil.which("curl")} "$@"'},
    )
    out = (tmp_path / "out").read_text()
    assert out.strip() == ("uv 0.13.4" if good else "uv 0.11.0"), (out, log)
    assert ("FAILED" not in log) == good, log
