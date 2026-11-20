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

ROOT = Path(__file__).resolve().parents[1]
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


def run_setup(tmp_path: Path, corrupt: str = "") -> tuple[str, Path, dict[str, str]]:
    """Run cloud-setup.sh against file:// release assets, in an empty mise home and a checkout pinning every tool
    but node (the one mise fetches itself), with mise's network refused and no other copy of a pinned tool on PATH. `corrupt` names an asset
    whose checksum list is wrong."""
    mise = shutil.which("mise")
    assert mise, "mise runs this suite"
    home, repo, releases, bin_ = (tmp_path / d for d in ("home", "repo", "releases", "bin"))
    for d in (home, repo, bin_):
        d.mkdir()
    publish(releases, release_assets(re.search(r"pbs=(\d+)", SETUP)[1]))
    if corrupt:
        for sums in releases.rglob(f"{corrupt}*.sha256"):
            sums.write_text("0" * 64 + sums.read_text()[64:])
    pins = {tool: pin for tool, pin in PINS.items() if tool != "node"}
    (repo / "mise.toml").write_text(
        "[tools]\n" + "".join(f'"{t}" = "{p}"\n' for t, p in pins.items())
    )
    for fake in ("apt-get", "codex", "ssh-keygen"):  # outside this test: the image's packages
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
        "CLOUD_SETUP_RELEASES": releases.as_uri(),
    }
    subprocess.run(
        ["bash", str(ROOT / ".claude" / "cloud-setup.sh")],
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


def test_a_checksum_mismatch_installs_nothing(tmp_path: Path) -> None:
    log, _repo, _env = run_setup(tmp_path, corrupt="uv-")
    assert "FAILED: uv" in log
    assert " uv" in log.split("FAILED, missing:")[1].split("\n")[0]
    assert not (tmp_path / "home" / ".local" / "share" / "mise" / "installs" / "uv").exists()


def test_mise_prefers_offline_before_it_installs() -> None:
    """Offline, mise counts the fetched tools as installed; online it exits 1 and drops them from a task's PATH (#1536)."""
    assert (
        -1
        < SETUP.find("step mise-offline mise settings set prefer_offline true")
        < SETUP.index("step mise-install ")
    )
