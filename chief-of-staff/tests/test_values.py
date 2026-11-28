from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff"
spec = importlib.util.spec_from_file_location("cos_values", SKILL / "scripts" / "cos_values.py")
cv = importlib.util.module_from_spec(spec)
sys.modules["cos_values"] = cv
spec.loader.exec_module(cv)

SAMPLES = {
    "first": SKILL / "references" / "values-first-setup.yml",
    "second": SKILL / "references" / "values-second-setup.yml",
}


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / cv.FILE_NAME
    p.write_text(text)
    return p


def test_no_file_gives_the_pack_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv(cv.ENV_VAR, raising=False)
    v = cv.load(home=tmp_path)
    assert v.file is None
    assert v.get("delegation.on") is False
    assert v.get("hygiene.repos") == []
    assert v.get("server") is None
    assert v.path("board") == tmp_path / "tmp/loop/chief-of-staff.md"
    assert v.path("registry") == tmp_path / "tmp/loop/leads.registry"


def test_file_is_plain_yaml_a_person_edits(tmp_path):
    p = _write(tmp_path, "# a comment the owner leaves\ndelegation:\n  on: true\n")
    v = cv.load(home=tmp_path)
    assert v.file == p and v.get("delegation.on") is True and v.is_set("delegation.on")
    assert not v.is_set("hygiene.repos")


def test_unknown_key_is_named_with_the_nearest(tmp_path):
    _write(tmp_path, "delegation:\n  onn: true\nregisty: x\n")
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    assert set(e.value.keys) == {"delegation.onn", "registy"}
    assert "delegation.onn: unknown key; did you mean `delegation.on`?" in str(e.value)
    assert "registy: unknown key; did you mean `registry`?" in str(e.value)


def test_unknown_key_on_get_is_named():
    with pytest.raises(cv.ValuesError, match="delegation.of: unknown key"):
        cv.load(home="/nonexistent-home").get("delegation.of")


def test_missing_key_is_named_by_require(tmp_path):
    v = cv.load(home=tmp_path)
    with pytest.raises(cv.ValuesError, match="cos_session: missing") as e:
        v.require("cos_session")
    assert e.value.keys == ("cos_session",)
    assert v.require("reports_dir") == "tmp/loop"


def test_wrong_type_and_choice_are_named(tmp_path):
    _write(
        tmp_path, "delegation: {on: yes please}\nhygiene: {repos: 5}\nmodels: {tiers: {boss: x}}\n"
    )
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    assert set(e.value.keys) == {"delegation.on", "hygiene.repos", "models.tiers.boss"}


def test_manager_missing_field_is_named(tmp_path):
    _write(tmp_path, "managers:\n  - scope: [repo-a]\n    board: b.md\n")
    with pytest.raises(cv.ValuesError, match=r"managers\[0\].registry: missing"):
        cv.load(home=tmp_path)


def test_group_must_be_a_mapping(tmp_path):
    _write(tmp_path, "hosts: [a]\n")
    with pytest.raises(cv.ValuesError, match="hosts: must be a mapping"):
        cv.load(home=tmp_path)


def test_named_file_must_exist(tmp_path, monkeypatch):
    with pytest.raises(cv.ValuesError, match="not found"):
        cv.load(tmp_path / "nope.yml")
    monkeypatch.setenv(cv.ENV_VAR, str(tmp_path / "nope.yml"))
    with pytest.raises(cv.ValuesError, match="not found"):
        cv.load(home=tmp_path)


def test_env_names_the_file(tmp_path, monkeypatch):
    p = tmp_path / "elsewhere.yml"
    p.write_text("delegation: {on: true}\n")
    monkeypatch.setenv(cv.ENV_VAR, str(p))
    assert cv.load().get("delegation.on") is True


def test_owner_only_adds_never_shortens(tmp_path):
    _write(tmp_path, "owner_only: [publish]\n")
    got = cv.load(home=tmp_path).get("owner_only")
    assert got[-1] == "publish" and set(cv.OWNER_ONLY) <= set(got)


def test_get_returns_a_copy(tmp_path):
    v = cv.load(home=tmp_path)
    v.get("hosts.table")["x"] = 1
    assert cv.KEYS["hosts.table"].default == {} and v.get("hosts.table") == {}


def test_path_keys_resolve_beside_board_or_home(tmp_path):
    _write(tmp_path, "board: boards/root.md\ndecisions: {file: /abs/d.md}\nreports_dir: in\n")
    v = cv.load(home=tmp_path)
    assert v.path("registry") == tmp_path / "boards/leads.registry"
    assert v.path("decisions.file") == Path("/abs/d.md")
    assert v.path("reports_dir") == tmp_path / "in"
    with pytest.raises(cv.ValuesError, match="server: not a path key"):
        v.path("server")


@pytest.mark.parametrize("setup", SAMPLES)
def test_sample_holds_only_that_setups_non_default_keys(setup, tmp_path):
    raw = yaml.safe_load(SAMPLES[setup].read_text())  # a sample is never empty
    v = cv.load(SAMPLES[setup])
    flat = {k for k in cv.KEYS if v.is_set(k)}
    # the sample loads, and every key it sets differs from the default
    for k in flat:
        key = cv.KEYS[k]
        if not key.extend:
            assert v.get(k) != key.default, f"{k} repeats its default"
    # it holds every key the inventory says this setup needs a non-default value for
    needed = {k.name for k in cv.KEYS.values() if setup in k.used_by}
    assert needed <= flat, sorted(needed - flat)
    assert raw


def test_defaults_hold_no_private_name_or_secret():
    for k in cv.KEYS.values():
        for s in _strings(k.default):
            assert "://" not in s and "@" not in s, k.name
            assert not s.startswith(("/", "~")) and not re.search(r"[A-Za-z]:\\", s), k.name
            assert not re.search(r"(?i)token|secret|password|\bsk-|ghp_", s), k.name
            assert not re.fullmatch(r"[A-Za-z0-9+/_-]{32,}", s), k.name
    for p in [*SAMPLES.values(), SKILL / "scripts" / "cos_values.py"]:
        text = p.read_text()
        assert not re.search(r"/(home|Users|root)/", text), p
        assert not re.search(r"\.ts\.net|ghp_|sk-[A-Za-z0-9]{10}", text), p


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _strings(k)
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


def test_every_key_default_passes_its_own_check():
    for k in cv.KEYS.values():
        if k.default is not None:
            errors: list = []
            cv._check_key(k, copy.deepcopy(k.default), errors)
            assert not errors, errors


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(cv.ENV_VAR, raising=False)
    _write(tmp_path, "delegation: {on: true}\n")
    assert cv.main(["--home", str(tmp_path), "get", "delegation.on"]) == 0
    assert capsys.readouterr().out.strip() == "true"
    assert cv.main(["--home", str(tmp_path), "get", "server"]) == 1
    assert "server: missing" in capsys.readouterr().err
    _write(tmp_path, "relaeses: x\n")
    assert cv.main(["--home", str(tmp_path), "check"]) == 1
    assert "relaeses: unknown key" in capsys.readouterr().err
    assert cv.main(["keys"]) == 0


def test_wrong_type_string_is_named(tmp_path):
    _write(tmp_path, "server: 5\ncos_session: ''\n")
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    assert set(e.value.keys) == {"server", "cos_session"}


def test_group_name_is_not_called_a_typo_of_itself(tmp_path):
    with pytest.raises(cv.ValuesError, match=r"hosts: unknown key \(a group, not a key") as e:
        cv.load(home=tmp_path).get("hosts")
    assert "did you mean" not in str(e.value)


def test_relative_home_resolves_to_absolute(tmp_path, monkeypatch):
    (tmp_path / "h").mkdir()
    monkeypatch.chdir(tmp_path)
    v = cv.load(home="h")
    monkeypatch.chdir("/")
    assert v.path("registry") == tmp_path / "h/tmp/loop/leads.registry"


def test_verifier_block_is_optional_and_checked(tmp_path, monkeypatch):
    monkeypatch.delenv(cv.ENV_VAR, raising=False)
    assert cv.load(home=tmp_path).get("verifier.route") is None
    _write(
        tmp_path, "verifier:\n  route: gemini\n  model: some-model\n  fallback: [codex, claude]\n"
    )
    v = cv.load(home=tmp_path)
    assert [v.get(f"verifier.{k}") for k in ("route", "model", "fallback")] == [
        "gemini",
        "some-model",
        ["codex", "claude"],
    ]
    _write(tmp_path, "verifier:\n  route: gpt\n  fallback: [codex, bard]\n  mode: x\n")
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    assert set(e.value.keys) == {"verifier.route", "verifier.fallback", "verifier.mode"}


def test_verifier_models_and_effort_are_keys_of_the_block(tmp_path, monkeypatch):
    monkeypatch.delenv(cv.ENV_VAR, raising=False)
    assert cv.load(home=tmp_path).get("verifier.effort") is None
    assert cv.load(home=tmp_path).get("verifier.models.default") is None
    _write(
        tmp_path,
        "verifier:\n  route: codex\n  models: {low: id-a, default: id-b}\n  effort: medium\n",
    )
    v = cv.load(home=tmp_path)
    assert [v.get(f"verifier.models.{k}") for k in ("low", "high", "default")] == [
        "id-a",
        None,
        "id-b",
    ]
    assert v.get("verifier.effort") == "medium"
    _write(tmp_path, "verifier:\n  models: {medium: id-a}\n  effort: [high]\n")
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    assert set(e.value.keys) == {"verifier.models.medium", "verifier.effort"}


DROPPED = [
    *("hosts." + k for k in ("cloud_bridge", "no_local_loop", "orchestration", "memory_floor")),
    "decisions.cos_line",
    "hygiene.retention_days",
    "hygiene.our_authors",
    "pin.notify",
    "pin.schedule",
    "deps.repos",
    "deps.schedule",
    "bridge.never_crosses",
    "data.allowed_hosts",
    "drafts_dir",
    "planning.backlog",
    "releases",
    "harness.default",
    "harness.codex_opt_in",
    "models.cap",
    "scheduled.cap_usd",
    "memory",
    "permissions.coordinator_mode",
    "prompts.cos_approves",
    "owner.language",
    "owner.reply_format",
]


@pytest.mark.parametrize("name", DROPPED)
def test_a_dropped_key_is_not_in_the_table_and_fails_as_unknown(name, tmp_path):
    assert name not in cv.KEYS
    group, _, leaf = name.partition(".")
    _write(tmp_path, f"{group}: {{{leaf}: x}}\n" if leaf else f"{name}: x\n")
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    # A group with no key left is unknown as a whole, and is the name the loader gives.
    named = name if any(k.startswith(group + ".") for k in cv.KEYS) or not leaf else group
    assert f"{named}: unknown key" in str(e.value)
