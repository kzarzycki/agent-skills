"""cloud-setup.sh installs what apm deploys, since settings.json's Bash hook fails closed without it (#1444)."""

from pathlib import Path

SETUP = (Path(__file__).resolve().parents[1] / ".claude" / "cloud-setup.sh").read_text()


def test_apm_install_follows_mise_install() -> None:
    assert SETUP.index("step mise-install ") < SETUP.index(
        "step apm-install mise exec -- apm install --frozen"
    )


def test_every_pinned_tool_but_node_is_fetched_before_mise_install() -> None:
    """mise resolves these through hosts the cloud proxy refuses (#1536); node comes from nodejs.org, which passes."""
    import tomllib

    tools = tomllib.loads((Path(__file__).resolve().parents[1] / "mise.toml").read_text())["tools"]
    install = SETUP.index("step mise-install ")
    for tool in set(tools) - {"node"}:
        assert (
            -1 < SETUP.find(f"pin {tool})") < install or -1 < SETUP.find(f'pin {tool}")') < install
        ), tool


def test_mise_prefers_offline_before_it_installs() -> None:
    """Offline, mise counts the fetched tools as installed; online it exits 1 and drops them from a task's PATH (#1536)."""
    assert (
        -1
        < SETUP.find("step mise-offline mise settings set prefer_offline true")
        < SETUP.index("step mise-install ")
    )
