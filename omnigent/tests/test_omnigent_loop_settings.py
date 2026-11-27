"""loop.md's `## Loop settings` block (#2830) as omnigent_agent.py reads it: every key it reads comes from the
gatekeeper's one loader (omnigent_agent holds no parser of the block), and a block that holds what the old lines held reads
the same through every reader."""

import subprocess
from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent

OLD = """# Loop

Cloud worker: claude-cloud, gate test, env dev
Placement: hosts: box, mac
Lead model: mid for size:S or smaller
Lead autocompact: 200k
Worker tools: WebFetch, github
Verifier tools: full
"""
BLOCK = """# Loop

## Loop settings

```yaml
cloud_worker:
  agent: claude-cloud
  gate: test
  env: dev
placement:
  hosts: [box, mac]
models:
  lead: mid for size:S or smaller
lead_autocompact: 200k
tools:
  worker: [WebFetch, github]
  verifier: full
```
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "docs" / "agents").mkdir(parents=True)
    return root


def write(repo: Path, text: str) -> str:
    (repo / "docs" / "agents" / "loop.md").write_text(text)
    return str(repo)


def test_cloud_worker_in_the_block_is_the_agent_gate_and_env() -> None:
    held = omnigent_agent.cloud_worker(BLOCK)
    assert held == omnigent_agent.CloudWorker("claude-cloud", "test", "dev")
    none = BLOCK.replace(
        "cloud_worker:\n  agent: claude-cloud\n  gate: test\n  env: dev\n", "cloud_worker: none\n"
    )
    assert omnigent_agent.cloud_worker(none) is None
    assert omnigent_agent.cloud_worker(
        "# Loop\n\n## Loop settings\n\n```yaml\ngate: full\n```\n"
    ) == (omnigent_agent.CloudWorker("claude-cloud", "", ""))


def test_placement_in_the_block_names_the_hosts_a_verifier_may_run_on(repo: Path) -> None:
    assert omnigent_agent.placement_hosts(write(repo, BLOCK)) == ["box", "mac"]
    ci = "# Loop\n\n## Loop settings\n\n```yaml\nplacement: CI\n```\n"
    assert omnigent_agent.placement_hosts(write(repo, ci)) == []


def test_models_lead_in_the_block_is_the_leads_tier_line(repo: Path) -> None:
    workspace = write(repo, BLOCK)
    assert omnigent_agent.project_line(workspace, "Lead model") == "mid for size:S or smaller"
    assert (
        omnigent_agent.lead_model("no issues named", workspace) is None
    )  # a line that parses, matching no issue
    bad = BLOCK.replace("mid for size", "huge for size")
    with pytest.raises(omnigent_agent.Fail, match="tier"):
        omnigent_agent.lead_model("x", write(repo, bad))


def test_lead_autocompact_in_the_block_is_the_window_the_lead_compacts_at(repo: Path) -> None:
    assert omnigent_agent.autocompact_args(write(repo, BLOCK)) == ["--autocompact", "200k"]


def test_lead_autocompact_out_of_range_in_the_block_fails_the_start(repo: Path) -> None:
    with pytest.raises(omnigent_agent.Fail, match="100k to 1M"):
        omnigent_agent.autocompact_args(write(repo, BLOCK.replace("200k", "50k")))


def test_tools_in_the_block_are_the_roles_beyond_the_lean_set(repo: Path) -> None:
    workspace = write(repo, BLOCK)
    worker = omnigent_agent.lean_args(workspace, "worker")
    assert worker[:2] == ["--strict-mcp-config", "--tools"] and "WebFetch" in worker[2].split(",")
    assert "github" in worker[2].split(",")
    assert omnigent_agent.lean_args(workspace, "verifier") == []  # `full`: every configured tool


def test_a_misspelt_key_in_the_block_fails_naming_it(repo: Path) -> None:
    with pytest.raises(omnigent_agent.Fail, match="lead_autocompct"):
        omnigent_agent.autocompact_args(
            write(repo, BLOCK.replace("lead_autocompact", "lead_autocompct"))
        )


def test_a_key_in_the_block_and_as_its_line_fails_naming_the_key(repo: Path) -> None:
    with pytest.raises(omnigent_agent.Fail, match="lead_autocompact"):
        omnigent_agent.autocompact_args(write(repo, BLOCK + "\nLead autocompact: 150k\n"))


def test_without_the_gatekeeper_a_block_is_refused_rather_than_read_as_no_line(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "_load_gatekeeper", lambda: None)
    with pytest.raises(omnigent_agent.Fail, match="gatekeeper"):
        omnigent_agent.placement_hosts(write(repo, BLOCK))
    assert omnigent_agent.placement_hosts(write(repo, OLD)) == [
        "box",
        "mac",
    ]  # the old lines need no loader


def test_the_old_lines_and_the_block_that_replaces_them_read_the_same(repo: Path) -> None:
    gk = omnigent_agent._load_gatekeeper()
    migrated = gk.loop_migrate(OLD)
    assert "## Loop settings" in migrated and "Placement:" not in migrated
    old, new = write(repo, OLD), None
    held = {
        "hosts": omnigent_agent.placement_hosts(old),
        "lead": omnigent_agent.project_line(old, "Lead model"),
        "compact": omnigent_agent.autocompact_args(old),
        "worker": omnigent_agent.lean_args(old, "worker"),
        "verifier": omnigent_agent.lean_args(old, "verifier"),
        "cloud": omnigent_agent.cloud_worker(OLD),
    }
    new = write(repo, migrated)
    assert held == {
        "hosts": omnigent_agent.placement_hosts(new),
        "lead": omnigent_agent.project_line(new, "Lead model"),
        "compact": omnigent_agent.autocompact_args(new),
        "worker": omnigent_agent.lean_args(new, "worker"),
        "verifier": omnigent_agent.lean_args(new, "verifier"),
        "cloud": omnigent_agent.cloud_worker(migrated),
    }
