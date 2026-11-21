"""approvals.py demo_form: a cloud session's REST demo, a blob link of the PR's own repo at a commit sha with
`?raw=true`, counts as embedded as a user-attachments one does; every other link stays refused (#1620)."""

from __future__ import annotations

import pytest
from approvals_harness import approvals, note, pull

SHA = "0123456789abcdef0123456789abcdef01234567"
REPO = "kzarzycki/scratch-gate-revert"


def demo(*urls: str) -> str:
    return "## Demo\n\nthe card, on aaaaaaa.\n" + "\n".join(urls) + "\n"


def lines(*comments: str | dict) -> list[str]:
    return approvals.demo_form(pull(comments=comments))


def blob(name: str = "card.png", repo: str = REPO, sha: str = SHA, query: str = "?raw=true") -> str:
    return f"https://github.com/{repo}/blob/{sha}/{name}{query}"


@pytest.mark.parametrize("ext", ["gif", "png", "jpg", "jpeg"])
def test_the_prs_own_sha_blob_raw_link_is_embedded_for_each_image_extension(ext: str) -> None:
    assert lines(demo(blob(f"card.{ext}"))) == []


@pytest.mark.parametrize("sha", [SHA.upper(), "0123456789ABCdef0123456789abcDEF01234567"])
def test_a_sha_of_either_hex_case_is_embedded(sha: str) -> None:
    assert lines(demo(blob(sha=sha))) == []


def test_the_repo_compares_case_insensitively() -> None:
    assert lines(demo(blob(repo=REPO.upper()))) == []


def test_a_markdown_image_of_the_blob_link_is_embedded() -> None:
    assert lines(demo(f"![card]({blob()})")) == []


@pytest.mark.parametrize(
    "url",
    [
        blob(repo="kzarzycki/other"),
        blob(repo="someone/scratch-gate-revert"),
        blob(sha="main"),
        blob(sha=SHA[:-1]),
        blob(sha=SHA + "0"),
        blob(query=""),
        blob(query="?raw=false"),
        blob(query="?raw=true&x=1"),
        blob(name="clip.mp4"),
        blob(name="dir/card.png"),
        blob(name=".png"),
        blob(name="card.webp"),
        blob(sha="g" * 40),
        blob(sha=SHA[:-1] + "z"),
        blob().replace("/blob/", "/tree/"),
        blob().replace("/blob/", "/raw/"),
        blob(name="card.png?x=y.png"),
        blob(name="card.png#x.png"),
        f"https://github.com/{REPO}/releases/download/demo-1/card.png",
        f"https://raw.githubusercontent.com/{REPO}/{SHA}/card.png",
        f"https://example.com/{REPO}/blob/{SHA}/card.png?raw=true",
        f"https://github.com.evil.test/{REPO}/blob/{SHA}/card.png?raw=true",
    ],
)
def test_every_other_link_stays_refused(url: str) -> None:
    found = lines(demo(url))
    assert len(found) == 1 and url in found[0]


def test_one_refused_link_among_accepted_ones_still_refuses() -> None:
    other = blob(repo="kzarzycki/other")
    found = lines(demo(blob(), other))
    assert len(found) == 1 and other in found[0]


def test_a_user_attachments_link_is_still_embedded() -> None:
    assert lines(demo("https://github.com/user-attachments/assets/0b1c-2d")) == []


def test_the_refusal_names_both_accepted_forms() -> None:
    found = lines(demo("https://example.com/x.mp4"))[0]
    assert "attachment" in found and "?raw=true" in found


def test_an_older_demo_edited_to_outdated_is_ignored() -> None:
    old = "Outdated, superseded by a newer demo.\n" + demo(blob(repo="kzarzycki/other"))
    assert lines(old, demo(blob())) == []
    assert lines(demo(blob()), old) == []
    assert lines(old) == []


def test_a_strangers_blob_demo_neither_holds_nor_clears() -> None:
    stranger = note(demo(blob(repo="kzarzycki/other")), author={"login": "drive-by"})
    assert lines(demo(blob()), stranger) == []
