"""cloud-setup.sh installs what apm deploys, since settings.json's Bash hook fails closed without it (#1444)."""

from pathlib import Path

SETUP = (Path(__file__).resolve().parents[1] / ".claude" / "cloud-setup.sh").read_text()


def test_apm_install_follows_mise_install() -> None:
    assert SETUP.index("step mise-install ") < SETUP.index(
        "step apm-install mise exec -- apm install --frozen"
    )
