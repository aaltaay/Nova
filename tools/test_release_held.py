"""A held Release opens one issue, and the next published Release closes it (operator report 2026-10-14)."""

from __future__ import annotations

import json

from tools import release_held


class FakeGh:
    def __init__(self, open_issues: list[dict] | None = None) -> None:
        self.open_issues = open_issues or []
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps(self.open_issues)
        if args[:2] == ["issue", "create"]:
            return "https://github.com/aaltaay/Nova/issues/999\n"
        return ""


def _never(url: str) -> None:
    raise AssertionError(f"nothing new to board, got {url}")


def test_without_the_project_token_the_issue_stays_filed_and_says_so(monkeypatch, capsys):
    monkeypatch.delenv(release_held.PROJECT_TOKEN_ENV, raising=False)
    release_held.board("https://github.com/aaltaay/Nova/issues/999")
    assert "NOVA_PROJECT_TOKEN is not set" in capsys.readouterr().out


def test_a_held_release_opens_one_p1_issue_with_the_gates_reason():
    gh = FakeGh()
    boarded: list[str] = []
    done = release_held.main(["open", "--tag", "v1297", "--sha", "9437f881abcdef12", "--run-url", "https://run"],
                             runner=gh, boarder=boarded.append)
    assert done == 0
    create = next(c for c in gh.calls if c[:2] == ["issue", "create"])
    assert create[create.index("--title") + 1] == "Release held: v1297 is not on the desk's update feed"
    labels = [create[i + 1] for i, arg in enumerate(create) if arg == "--label"]
    assert labels == ["deferred", "bug", "P1", "domain:ci"]
    # Review of PR #950: a GITHUB_TOKEN issue triggers no inbox or board workflow, so it is routed here.
    assert create[create.index("--milestone") + 1] == "00 - Untriaged"
    assert boarded == ["https://github.com/aaltaay/Nova/issues/999"]
    text = create[create.index("--body") + 1]
    assert "**v1297**" in text and "`9437f881abcd`" in text and "https://run" in text


def test_a_re_run_held_again_comments_on_its_own_issue():
    gh = FakeGh([{"number": 950, "title": "Release held: v1297 is not on the desk's update feed"},
                 {"number": 12, "title": "Something else mentioning Release held: in the body"}])
    assert release_held.report(gh, "v1297", "abc", "https://run2", "### v1297 not published",
                               boarder=_never) == "commented on #950"
    assert not any(c[:2] == ["issue", "create"] for c in gh.calls)
    comment = next(c for c in gh.calls if c[:2] == ["issue", "comment"])
    assert comment[2] == "950" and "v1297 not published" in comment[comment.index("--body") + 1]


def test_another_held_tag_gets_its_own_issue():
    gh = FakeGh([{"number": 950, "title": "Release held: v1297 is not on the desk's update feed"}])
    boarded: list[str] = []
    assert release_held.report(gh, "v1298", "abc", "https://run2", "", boarder=boarded.append).startswith("opened ")
    assert boarded == ["https://github.com/aaltaay/Nova/issues/999"]


def test_a_published_release_closes_its_own_and_older_held_issues_only():
    gh = FakeGh([{"number": 950, "title": "Release held: v1297 is not on the desk's update feed"},
                 {"number": 951, "title": "Release held: v1300 is not on the desk's update feed"}])
    assert release_held.resolve(gh, "v1299") == [950]                 # v1300 finished out of order: still held
    close = next(c for c in gh.calls if c[:2] == ["issue", "close"])
    assert close[2] == "950" and "v1299 published" in close[close.index("--comment") + 1]


def test_nothing_held_closes_nothing():
    gh = FakeGh()
    assert release_held.resolve(gh, "v1299") == []
    assert [c[:2] for c in gh.calls] == [["issue", "list"]]
