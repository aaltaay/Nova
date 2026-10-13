"""A vNNN Release publishes only from a green build (operator decision 2026-10-13)."""

from __future__ import annotations

import json

import pytest

from tools.release_gate import (
    CHECKS_PREFIX,
    REQUIRED_CHECKS,
    headline,
    load_jobs,
    main,
    verdict,
)


def job(check: str, conclusion: str | None = "success", *, status: str = "completed",
        attempt: int = 1, job_id: int = 1, prefix: str = CHECKS_PREFIX) -> dict:
    return {"id": job_id, "name": f"{prefix} / {check}", "status": status,
            "conclusion": conclusion, "run_attempt": attempt}


def green_run() -> list[dict]:
    jobs = [job(check, job_id=i) for i, check in enumerate(REQUIRED_CHECKS, start=10)]
    # Warning-only and PR-only jobs never hold a Release.
    jobs += [
        job("security / Semgrep", "failure", job_id=50),
        job("Auto-merge", "skipped", job_id=51),
        {"id": 52, "name": "Desktop pack", "status": "completed", "conclusion": "success"},
        {"id": 53, "name": "Publish vNNN installer", "status": "in_progress", "conclusion": None},
    ]
    return jobs


def test_a_green_build_publishes():
    assert verdict(green_run(), "success") == []
    assert headline("v812", []).startswith("v812: the installer packed")


def test_the_four_verification_jobs_gate_the_release():
    """The jobs CI runs on every PR -- master's required checks until 2026-09-20."""
    assert REQUIRED_CHECKS == ("Backend tests", "Frontend build", "Frontend E2E", "Agent contract")


@pytest.mark.parametrize("conclusion, words", [
    ("failure", "failed"),
    ("cancelled", "was cancelled"),
    ("timed_out", "timed out"),
    ("skipped", "was skipped"),
    ("startup_failure", "failed to start"),
    (None, "has no result"),
])
def test_anything_but_success_holds_the_release(conclusion, words):
    jobs = [j for j in green_run() if j["name"] != f"{CHECKS_PREFIX} / Backend tests"]
    jobs.append(job("Backend tests", conclusion, job_id=99))
    assert verdict(jobs, "success") == [("Backend tests", words)]


def test_a_skipped_check_is_not_a_green_one():
    """Scope-skipped tests on an application-affecting commit must never ship it."""
    jobs = [j for j in green_run() if j["name"] != f"{CHECKS_PREFIX} / Frontend E2E"]
    jobs.append(job("Frontend E2E", "skipped"))
    assert verdict(jobs, "success") == [("Frontend E2E", "was skipped")]


def test_a_missing_or_unfinished_check_holds_the_release():
    jobs = [j for j in green_run() if j["name"] != f"{CHECKS_PREFIX} / Agent contract"]
    assert verdict(jobs, "success") == [("Agent contract", "did not run")]
    jobs.append(job("Agent contract", None, status="in_progress"))
    assert verdict(jobs, "success") == [("Agent contract", "is still in_progress")]


def test_only_the_release_checks_count_not_a_same_named_job_elsewhere():
    """A PR run's bare `Backend tests` is another commit's verdict, not this one's."""
    jobs = [j for j in green_run() if j["name"] != f"{CHECKS_PREFIX} / Backend tests"]
    jobs.append({"id": 7, "name": "Backend tests", "status": "completed", "conclusion": "success"})
    assert verdict(jobs, "success") == [("Backend tests", "did not run")]


def test_the_call_counts_under_its_job_id_as_well_as_its_name():
    jobs = [j for j in green_run() if not j["name"].startswith(CHECKS_PREFIX)]
    jobs += [job(check, prefix="verify", job_id=i) for i, check in enumerate(REQUIRED_CHECKS, start=60)]
    assert verdict(jobs, "success") == []


def test_a_failed_or_missing_pack_holds_the_release():
    assert verdict(green_run(), "failure") == [("Desktop pack", "failed")]
    assert verdict(green_run(), "") == [("Desktop pack", "has no result")]


def test_a_green_rerun_counts_and_a_red_rerun_wins_over_an_old_green():
    jobs = green_run()
    jobs.append(job("Backend tests", "failure", attempt=1, job_id=5))
    jobs = [j for j in jobs if not (j["name"].endswith("/ Backend tests") and j["id"] != 5)]
    assert verdict(jobs, "success") == [("Backend tests", "failed")]
    jobs.append(job("Backend tests", "success", attempt=2, job_id=6))
    assert verdict(jobs, "success") == []
    jobs.append(job("Backend tests", "failure", attempt=3, job_id=8))
    assert verdict(jobs, "success") == [("Backend tests", "failed")]


def test_every_reason_is_named_in_one_line():
    jobs = [j for j in green_run() if not j["name"].endswith(("/ Backend tests", "/ Frontend E2E"))]
    jobs += [job("Backend tests", "failure"), job("Frontend E2E", "cancelled")]
    held = verdict(jobs, "failure")
    assert headline("v812", held) == (
        "v812 not published: Desktop pack failed; Backend tests failed; Frontend E2E was cancelled"
    )


def test_paginated_slurped_and_bare_listings_all_load():
    jobs = green_run()
    pages = [{"total_count": len(jobs), "jobs": jobs[:3]}, {"total_count": len(jobs), "jobs": jobs[3:]}]
    concatenated = "".join(json.dumps(page) for page in pages)
    assert load_jobs(concatenated) == jobs
    assert load_jobs("\n".join(json.dumps(page) for page in pages)) == jobs
    assert load_jobs(json.dumps(pages)) == jobs
    assert load_jobs(json.dumps(jobs)) == jobs
    with pytest.raises(ValueError):
        load_jobs(json.dumps({"message": "Not Found"}))


def test_main_publishes_green_and_holds_red_with_a_visible_reason(tmp_path, capsys, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    listing = tmp_path / "jobs.json"
    listing.write_text(json.dumps({"jobs": green_run()}), encoding="utf-8")
    assert main(["--tag", "v812", "--pack", "success", "--jobs-file", str(listing)]) == 0
    assert "every release check is green" in summary.read_text(encoding="utf-8")

    red = [j for j in green_run() if not j["name"].endswith("/ Backend tests")]
    red.append(job("Backend tests", "failure"))
    listing.write_text(json.dumps({"jobs": red}), encoding="utf-8")
    assert main(["--tag", "v813", "--pack", "success", "--jobs-file", str(listing)]) == 1
    out = capsys.readouterr().out
    assert "::error title=v813 not published::v813 not published: Backend tests failed" in out
    written = summary.read_text(encoding="utf-8")
    assert "### v813 not published: Backend tests failed" in written
    assert "gh workflow run desktop-pack.yml --ref v813" in written


def test_main_fails_closed_when_the_checks_cannot_be_read(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    missing = tmp_path / "absent.json"
    assert main(["--tag", "v814", "--pack", "success", "--jobs-file", str(missing)]) == 1
    assert "v814 not published: Release checks could not be read" in capsys.readouterr().out
    garbage = tmp_path / "garbage.json"
    garbage.write_text("<html>rate limited</html>", encoding="utf-8")
    assert main(["--tag", "v814", "--pack", "failure", "--jobs-file", str(garbage)]) == 1
    assert "Desktop pack failed; Release checks could not be read" in capsys.readouterr().out
