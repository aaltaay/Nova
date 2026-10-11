"""The Sim import's hard memory cap (operator report 2026-10-11): a read that keeps too much fails its own
import with the reason, never takes the PC's memory from the API, IB Gateway and the desk."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from constants_sim import SIM_MASSIVE_WORKER_MEMORY_ENV, SIM_MASSIVE_WORKER_MEMORY_MB
from sim import massive_worker
from winapi import job_limit

BACKEND = Path(__file__).resolve().parents[1]


def test_a_run_into_the_cap_says_so_with_the_setting_that_raises_it():
    assert massive_worker.why_failed(MemoryError(), 6144) == (
        "The import used its whole 6,144 MB memory cap and was stopped before writing anything "
        f"({SIM_MASSIVE_WORKER_MEMORY_ENV} raises it)")
    assert massive_worker.why_failed(MemoryError(), None) == "MemoryError"     # no cap: no claim of one
    assert massive_worker.why_failed(ValueError("The Massive trades file is not on disk"), 6144) == (
        "The Massive trades file is not on disk")


@pytest.mark.parametrize(("raw", "expected"), [("", SIM_MASSIVE_WORKER_MEMORY_MB), ("2048", 2048),
                                                ("lots", SIM_MASSIVE_WORKER_MEMORY_MB), ("0", None)])
def test_the_cap_is_the_constant_or_the_setting(monkeypatch, raw, expected):
    asked = []
    monkeypatch.setenv(SIM_MASSIVE_WORKER_MEMORY_ENV, raw)
    monkeypatch.setattr(job_limit, "cap_this_process", lambda limit: asked.append(limit) or True)
    assert massive_worker._cap_memory() == expected
    assert asked == ([expected * 2**20] if expected else [])


def test_a_cap_windows_refuses_runs_uncapped_and_says_so(monkeypatch, caplog):
    def refuse(limit):
        raise OSError(5, "Access is denied")

    monkeypatch.delenv(SIM_MASSIVE_WORKER_MEMORY_ENV, raising=False)
    monkeypatch.setattr(job_limit, "cap_this_process", refuse)
    assert massive_worker._cap_memory() is None
    assert "runs uncapped" in caplog.text


@pytest.mark.skipif(sys.platform != "win32", reason="a Windows job object")
def test_past_the_cap_an_allocation_fails_and_the_process_lives_on():
    probe = textwrap.dedent("""
        from winapi import job_limit
        assert job_limit.cap_this_process(200 * 2**20)
        held = [bytearray(40 * 2**20)]
        try:
            held += [bytearray(40 * 2**20) for _ in range(10)]
            print("uncapped")
        except MemoryError:
            held.clear()
            again = bytearray(100 * 2**20)
            print("capped", len(again) // 2**20)
    """)
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(BACKEND), capture_output=True, text=True,
                          timeout=60, check=False)
    assert done.stdout.strip() == "capped 100", done.stderr
