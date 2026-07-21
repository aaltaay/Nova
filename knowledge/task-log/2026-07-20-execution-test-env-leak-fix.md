# 2026-07-20 — Execution/executor/routes-trading tests leaked real env + real bootstrap

- **Status:** completed
- **Agents:** parent
- **Domain:** execution (audit-only domain touched only its own test files)
- **Related:** `CHANGELOG.md` "Root-cause fix: execution/executor/routes-trading tests leaked real env + real bootstrap" · `PROBLEM_LOG.md` "18 execution/executor/routes-trading tests failed after switching Gateway to live" · Nova roadmap gap closure plan step 1

## Task

While following the Nova roadmap gap-closure plan, a fresh `pytest` run surfaced 19 backend failures. The plan called these out as a real bug (not pre-existing flake) and required a root-cause fix before trusting the verification baseline or shipping the accumulated uncommitted backlog.

## Goal

Find the actual root cause of the 18 execution/executor/routes-trading failures (1 remaining `test_hod_momo_universe.py` failure is pre-existing and out of scope) and fix it at the source, not by resetting the environment and hoping it doesn't recur.

## Why it mattered

These are the tests that guard ADR 007's centralized order-placement path — exactly the code Phase B (paper shadow trading) depends on. A test suite that silently depends on the developer's real `.env` `IBKR_GATEWAY_MODE` value means "green tests" stop being trustworthy the moment anyone (agent or human) touches that env var for unrelated ops debugging — which is exactly what happened earlier in this session while diagnosing an IBKR disconnect issue.

## What we changed

- `backend/tests/test_execution_service.py`: `_arm_paper()` now does `monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")`; its `isolated_execution` autouse fixture now also calls `strategy.risk.reset_day()` on setup/teardown.
- `backend/tests/test_executor.py`: `_arm_ibkr_execution()` now does the same `setenv`; `reset_executor_state` autouse fixture also resets `strategy.risk`.
- `backend/tests/test_routes_trading.py`: `_arm_paper_gates()` adds `patch.dict(os.environ, {"IBKR_GATEWAY_MODE": "paper"})` as an 8th context manager (all 4 call sites updated to include it); `isolated_execution_ledger` fixture now also isolates `journal.db.cache_dir` / `nova_os.events_db.cache_dir` to `tmp_path` and stubs `app_lifespan._bootstrap_runtime` with `AsyncMock()`.

## How it works now

`ibkr/safety.py::assert_orders_allowed()` reads `gateway_mode()` — a direct `os.environ.get("IBKR_GATEWAY_MODE", ...)` read — independently of the `client_mod.account_mode()` / `broker_account_kind()` mocks tests already had. Any "paper" test helper that doesn't also pin the env var is only paper-safe by accident, as long as the ambient `.env` happens to say paper. All three helpers now pin it explicitly, so these tests are deterministic regardless of the real `.env`.

Separately, `test_routes_trading.py` has a **module-level** `client = TestClient(app)`. The first request any test in that file makes lazily fires `main.py`'s real FastAPI lifespan, which schedules `app_lifespan._bootstrap_runtime()` as a background `asyncio.create_task` — real IBKR ping, `strategy.risk.reconstruct_from_journal()`, `nova_os.recovery.run_startup_recovery()`. Because the file's isolation fixture only patched `execution.store.cache_dir` (not `journal.db`/`events_db`), that background task read the **real** on-disk journal and could replay real trade history into the process-global `strategy.risk._state` singleton — tripping its loss-halt guardrail for the rest of the pytest session. Confirmed independently: `backend/.cache/execution_ledger.db` had 353 real accumulated rows before this fix. The fixture now isolates the remaining cache paths and no-ops the background bootstrap entirely — these are route-wiring tests that already mock the IBKR/execution boundary, so the real bootstrap has nothing to verify.

## Why this approach

Two real, independent bugs were compounding into one symptom, so a single fix (e.g. just resetting `.env`) would have looked like it worked while leaving both leaks live for the next person who changes `IBKR_GATEWAY_MODE`. Rejected: (a) just setting `.env` back to paper and moving on — this is the roadmap's step-3 action anyway, but it wouldn't have prevented recurrence, violating the self-annealing "fix the root cause, not the symptom" rule; (b) making `_arm_paper_gates()` monkeypatch `safety_mod.gateway_mode` directly (tried first) — this silently broke `TestPaperLiveParity::test_same_execute_path[live]`, which deliberately does its own later `monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")` to test the live branch; patching the function object shadows that override, while `setenv`/`patch.dict(os.environ, ...)` composes correctly because later `setenv` calls simply layer on top; (c) not touching `test_routes_trading.py`'s lifespan/bootstrap issue since the env fix alone made the reproducer pass — left as unfixed, the module-level `TestClient` would keep firing a real, unawaited background task on first use in every future run, an unrelated future test could still trip the same `strategy.risk` singleton non-deterministically depending on real journal contents on whatever machine runs the suite next.

## Verification

- `pytest tests/test_execution_service.py tests/test_executor.py tests/test_routes_trading.py` → 59 passed (was 18 failed / 41 passed).
- Full backend `pytest` → 847 passed, 1 pre-existing unrelated failure (`test_hod_momo_universe.py::test_build_focus_universe_empty_inputs`), consistent count with the original 19-failure baseline minus these 18.
- Confirmed `TestPaperLiveParity::test_same_execute_path[live]` still exercises the real live branch correctly after switching from a function-patch to `setenv`.

## Follow-ups

- `backend/.cache/execution_ledger.db` (353 rows) still needs a one-time inspection to separate genuine manual paper-order test rows from any residual test pollution written before this fix — not touched here to avoid destroying real ledger history; deferred to the roadmap gap-closure plan's later steps.
- Do not reopen the env-mocking fix in `_arm_paper_gates()` by patching `safety_mod.gateway_mode` directly — use `patch.dict(os.environ, ...)` / `monkeypatch.setenv` only, to keep composing correctly with tests that intentionally override the mode.

## Keywords

IBKR_GATEWAY_MODE, gateway_mode, assert_orders_allowed, TestClient lifespan, app_lifespan, _bootstrap_runtime, strategy.risk singleton, execution_ledger.db, test isolation, cross-file pollution, ADR 007
