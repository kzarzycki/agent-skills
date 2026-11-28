"""The environment variables a test run must not see, one list for the root `conftest.py` and the repo test that
checks it (tests/test_env_reads.py, #2455).

A test sees the same environment wherever it runs: on a host, in a cloud VM, in a PR's CI, in the merge queue. The
root conftest clears every variable here before each test, and a test that needs one sets it itself. Product code
under `tools/` and a package's `scripts/` that reads an environment variable by literal name must find the name in
RUNNER, SESSION, SESSION_PREFIXES or HOST_NEUTRAL, so a new read is decided when it is written, not after a queue run
fails.
"""

# Where the run happens: the merge queue's batch (GITHUB_HEAD_REF under `mergify/merge-queue/`, GATE_IN_QUEUE) and the
# runner's own variables, which product code reads to pick a policy or an output.
RUNNER = (
    "GATE_IN_QUEUE",
    "GITHUB_ACTIONS",
    "GITHUB_API_URL",
    "GITHUB_EVENT_NAME",
    "GITHUB_HEAD_REF",
    "GITHUB_OUTPUT",
    "GITHUB_REF_NAME",
    "GITHUB_REPOSITORY",
    "GITHUB_SHA",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_TOKEN",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKSPACE",
    "REPO",
    "RUN_JSON",
)

# Which agent session the run is in: an Omnigent session, a cloud VM's marker, the host's model and effort defaults.
SESSION = (
    "OMNIGENT_RUNNER_PRIMARY_SESSION_ID",
    "OMNIGENT_SESSION_ID",
    "OMNIGENT_TERMINAL_LAUNCH_SESSION_ID",
    "LOOP_HEAVY_LOCK",
    "OMNIGENT_PERMISSION_MODE",
    "OMNIGENT_RUNNER_TOKEN",  # cloud_verifier.py reads it; main's own test_env_reads was red on it (#2804)
    "CLAUDE_CODE_REMOTE",
)
SESSION_PREFIXES = ("OMNIGENT_MODEL_", "OMNIGENT_EFFORT_")

# Read by name and left alone: the user's home and tool locations, and tuning knobs a host sets on purpose. A test that
# depends on one sets it itself.
HOST_NEUTRAL = (
    "AGENT_HOST_COMMANDS",
    "OMNIGENT_DATA_DIR",  # the host data dir a script reads for its own state; main already reads it (#2679)
    # the root conftest.py sets it to 1 for the whole run, as the pack's own tests need; clearing it would undo that
    "AGENT_SKILLS_CHECKOUT",
    "CDP_URL",
    "CLAUDE_CDP_PORT",
    "CLAUDE_CLOUD_API_BASE",
    "COVERAGE_FILE",  # the nightly's coverage data file, which tools/shard_plugin.py splits across its shards (#2804)
    "CODEX_CLOUD_HOME",
    "CODEX_CLOUD_USAGE",
    "CODEX_CLOUD_WS",
    "CODEX_HOME",
    "GATEKEEPER_REST_ONLY",
    "GATE_DURATIONS",
    "GATE_INCUBATING",
    "GATE_INCUBATING_WAIVES",
    "GATE_JOBS",
    "GATE_SETUP_SECONDS",
    "GATE_SLOTS",
    "GATE_WORKERS",
    "GH_QUOTA_LOG",
    "GIT_CEILING_DIRECTORIES",
    "HINDSIGHT_API_URL",
    "HINDSIGHT_CONFIG",
    "HOME",
    "LOOP_NOTIFY",
    "OMNIGENT_CAPACITY_WAIT_SECONDS",
    "RELEASE_SMOKE_PR",  # the on-demand smoke-run command's `pr` input, set by the caller (#1454)
    "OMNIGENT_CLOUD_MIN_AVAILABLE_MB",
    "OMNIGENT_MAX_LOAD_PER_CORE",
    "OMNIGENT_MIN_AVAILABLE_MB",
    "OMNIGENT_MIN_CPU_IDLE",
    "OMNIGENT_PROJECT",
    "OMNIGENT_SMALL_MODEL",
    "OMNIGENT_STUCK_SECONDS",
    "OMNIGENT_SUPERVISE_REGISTRY",
    "OMNIGENT_VERIFIER_ROUTE",
    "PATH",
    "PYTEST_ADDOPTS",
    "PYTEST_TIMEOUT",
    "RUNNER_SERVER_URL",
    "TEST_MAP",
    "USER",
    "UV_RUN_RECURSION_DEPTH",
    "VIRTUAL_ENV",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "environmentId",
)


def covered(name: str) -> bool:
    """Whether a variable read by literal name is cleared for tests or listed as host-neutral."""
    return (
        name in RUNNER
        or name in SESSION
        or name in HOST_NEUTRAL
        or name.startswith(SESSION_PREFIXES)
    )
