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
    assert v.get("releases") == "held"
    assert v.get("hygiene.retention_days") == 14
    assert v.get("server") is None
    assert v.path("board") == tmp_path / "tmp/loop/chief-of-staff.md"
    assert v.path("registry") == tmp_path / "tmp/loop/leads.registry"


def test_file_is_plain_yaml_a_person_edits(tmp_path):
    p = _write(tmp_path, "# a comment the owner leaves\ndelegation:\n  on: true\n")
    v = cv.load(home=tmp_path)
    assert v.file == p and v.get("delegation.on") is True and v.is_set("delegation.on")
    assert not v.is_set("releases")


def test_unknown_key_is_named_with_the_nearest(tmp_path):
    _write(tmp_path, "delegation:\n  onn: true\nrelease: held\n")
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    assert set(e.value.keys) == {"delegation.onn", "release"}
    assert "delegation.onn: unknown key; did you mean `delegation.on`?" in str(e.value)
    assert "release: unknown key; did you mean `releases`?" in str(e.value)


def test_unknown_key_on_get_is_named():
    with pytest.raises(cv.ValuesError, match="delegation.of: unknown key"):
        cv.load(home="/nonexistent-home").get("delegation.of")


def test_missing_key_is_named_by_require(tmp_path):
    v = cv.load(home=tmp_path)
    with pytest.raises(cv.ValuesError, match="cos_session: missing") as e:
        v.require("cos_session")
    assert e.value.keys == ("cos_session",)
    assert v.require("releases") == "held"


def test_wrong_type_and_choice_are_named(tmp_path):
    _write(tmp_path, "delegation: {on: yes please, max_risk: huge}\nmodels: {tiers: {boss: x}}\n")
    with pytest.raises(cv.ValuesError) as e:
        cv.load(home=tmp_path)
    assert set(e.value.keys) == {"delegation.on", "delegation.max_risk", "models.tiers.boss"}


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
    p.write_text("releases: continuous\n")
    monkeypatch.setenv(cv.ENV_VAR, str(p))
    assert cv.load().get("releases") == "continuous"


def test_owner_only_adds_never_shortens(tmp_path):
    _write(tmp_path, "owner_only: [publish]\n")
    got = cv.load(home=tmp_path).get("owner_only")
    assert got[-1] == "publish" and set(cv.OWNER_ONLY) <= set(got)


def test_get_returns_a_copy(tmp_path):
    v = cv.load(home=tmp_path)
    v.get("hosts.table")["x"] = 1
    assert cv.KEYS["hosts.table"].default == {} and v.get("hosts.table") == {}


def test_path_keys_resolve_beside_board_or_home(tmp_path):
    _write(
        tmp_path, "board: boards/root.md\ndecisions: {file: /abs/d.md}\nbridge: {inbox_dir: in}\n"
    )
    v = cv.load(home=tmp_path)
    assert v.path("registry") == tmp_path / "boards/leads.registry"
    assert v.path("decisions.file") == Path("/abs/d.md")
    assert v.path("bridge.inbox_dir") == tmp_path / "in"
    with pytest.raises(cv.ValuesError, match="drafts_dir: missing"):
        v.path("drafts_dir")
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
    _write(tmp_path, "releases: continuous\n")
    assert cv.main(["--home", str(tmp_path), "get", "releases"]) == 0
    assert capsys.readouterr().out.strip() == '"continuous"'
    assert cv.main(["--home", str(tmp_path), "get", "server"]) == 1
    assert "server: missing" in capsys.readouterr().err
    _write(tmp_path, "relaeses: held\n")
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
