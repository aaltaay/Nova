# Code Rules Rewrite Implementation Plan

> **Status (2026-09-23): done, with changes.** Task 1's logical-line entry points shipped with #393; the rest landed in the file-size / scalability rules PR. Differences from this plan: size is a soft 400 that asks for a one-concern reason plus a growth check and an 800 ceiling on every file (not a money-path size tier); the money-path list is `execution/`, `ibkr/`, `practice/`, `sim/`, `kill_switch/`, `bot/`, `frontend/src/ibkr/` (Nova OS was retired by ADR 025); cross-feature imports are frozen per file for every `feature` in `frontend/src/FOLDERS.md`; §3 contracts stayed in AGENTS.md. Read AGENTS.md §2 and §6.3, not this plan.

**Goal:** Replace the code-shape rules in `AGENTS.md` §2 and the invariants that feed them with behavior rules that cannot go stale, tier size and error-handling strictness by whether a module touches money, and make `tools/maintainer_checks.py` the single enforced source of those rules in CI. Closes #393 as a consequence, not as the point.

**Architecture:** No product behavior changes except in Task 3, where 18 silent `except` sites on the money path gain, at minimum, a logged warning. Everything else is tooling (`tools/maintainer_checks.py`, its tests, one CI step), constitution text (`AGENTS.md`, five `.cursor/rules/*.mdc`), and a doc move (`AGENTS.md` §3 → `architecture/contracts/`).

**Tech stack:** Python 3.13 (`tools/`, pytest), GitHub Actions (`.github/workflows/deploy.yml`), Markdown.

**Nova constraints:** single IBKR feed (untouched) | execution gates (untouched — Task 3 only adds logging inside `except` blocks; it never changes what is raised or returned) | modularity (this plan rewrites the modularity rule itself; §2.4 refactoring protocol is kept verbatim) | file limits (rewritten to logical-line and money-path tiers) | no `auto_live` (untouched).

## Global constraints

- Three PRs, in order. PR 1 (Tasks 1–2) is tooling + CI and touches no product code. PR 2 (Task 3) fixes the 18 money-path sites and flips the new kinds to CI-blocking. PR 3 (Tasks 4–7) rewrites the constitution text and closes #393. Each PR is independently revertible; reverting PR 3 alone leaves the tooling and fixes in place.
- Every task ends with a runnable `Verify` command whose expected output is stated. Do not claim a task done without pasting that output into the PR body (`verification-before-completion.mdc`).
- `AGENTS.md` §1 #8: constitution changes land in the same PR as the code they govern. PR 3 carries the maintenance-log row. PRs 1 and 2 do not edit `AGENTS.md`.
- Never edit `CHANGELOG.md` (§7.1, generated). Each PR body carries What / Why / Verified by.
- Stage explicit paths. No `git add -A`. One worktree per PR (`workspace-hygiene.mdc`).
- Advisory verification (§5, 2026-09-20): CI red does not block merge, but this plan deliberately sequences PR 2 before flipping any kind to blocking so master is never red *because of this plan*.

## Why this plan exists (evidence, all reproducible on `master` at `b92b9ad`)

Run each command from the repo root. Numbers below are what they printed on 2026-09-20.

| Claim | Command | Result |
|---|---|---|
| The "enforced file structure" in §2.1/§2.2 describes files that do not exist | `for f in backend/market.py backend/alpaca.py backend/cache.py backend/scanner.py backend/news.py backend/fundamentals.py backend/websocket.py backend/hod_momo.py backend/bars.py backend/routes/health.py backend/routes/scan.py backend/routes/ticker.py backend/routes/settings.py frontend/src/components/GapperTable.tsx frontend/src/components/GainerTable.tsx frontend/src/components/LoserTable.tsx frontend/src/components/NewsCatalystPanel.tsx frontend/src/components/TickerDetail.tsx frontend/src/components/SettingsPanel.tsx frontend/src/components/HealthBadge.tsx frontend/src/hooks/useWebSocket.ts frontend/src/hooks/useGappers.ts frontend/src/pages/DashboardPage.tsx frontend/src/pages/SettingsPage.tsx; do [ -e "$f" ] \|\| echo "MISSING $f"; done \| wc -l` | **11 of 24 missing.** Backend has 104 top-level modules and 25 subpackages, not the ~15 listed. |
| The entry-point fight is won; the numbers measure imports and comments now | `wc -l backend/main.py frontend/src/App.tsx` | `main.py` **40** / limit 200. `App.tsx` **152** / limit 150 — of which 30 imports, 14 comments, 8 blank, **100 logical**. |
| CI computes every finding and discards all but one kind | `sed -n '243,247p' .github/workflows/deploy.yml` | `--fail-on-kind ib_loop_sync_io` only. |
| The test that catches the breach is not in CI | `grep -c test_maintainer_checks .github/workflows/deploy.yml` | **0**. (The tools pytest list at `deploy.yml:232` names 22 files by hand; this one is not among them.) |
| The 400-line rule is mostly right about which files are big | `python3 tools/maintainer_checks.py --json` → filter `kind == "file_size"` | **22** findings; 18 are logic, 4 are constants/CSS/tests. |
| §6.3 "never swallow exceptions" is violated most where it matters most | same JSON → `kind in {swallowed_exception, except_return_empty, empty_promise_catch}` | **40** findings; **18 on the money path** (list in Task 3). |
| Invariant #5 "SOP before code" drags a rule edit into half of product work | `for c in $(git rev-list HEAD -40); do git show --name-only --format= $c; done` grouped | 12 product commits in the window; **6** also edited `AGENTS.md` or `.cursor/rules/`. |
| §3 grows with every endpoint | `sed -n '163,271p' AGENTS.md \| grep -cE '^###\|^```json'` | **6** contract blocks living in the constitution. |

Full finding counts from `maintainer_checks.py --json` on that SHA: 48 `cross_feature_import`, 24 `swallowed_exception`, 22 `file_size`, 12 `except_return_empty`, 4 `empty_promise_catch`, 1 `file_size_hard`, 1 `import_main`. The 48 `cross_feature_import` findings are out of scope here (see *Out of scope*).

## Why this approach (tradeoffs and rejected alternatives)

**Logical lines for entry points, not a raised raw limit.** Raising `APP_TSX_LIMIT` to 250 passes today and fails the next time the app gains four providers. Deleting the limit leaves only the generic 300-line `.tsx` cap, which needs +148 lines of creep before anything fires. Counting non-blank, non-import, non-comment lines measures the invariant the rule exists for ("entry points hold wiring only") and gives `App.tsx` 100/150 — real headroom, and an alarm that still trips on 50 lines of actual logic.

**Tier by money path, not one number for the tree.** `backend/execution/service.py` (the sole broker-mutation entry under ADR 007, 404 lines) and `frontend/src/chart/ChartContextMenu.tsx` (307 lines) are not the same risk. A uniform 400 either nags the chart menu or under-guards the order path. Two tiers: generic `file_size` stays advisory; `file_size_money` is blocking for new entrants and for growth past a baseline.

**Baseline the 7 oversize money-path files; fix the 18 swallowed exceptions.** A baseline for size is honest — splitting `ibkr/discovery.py` (714) is real work that deserves its own issue and should not be forced by a linter PR. A baseline for silent `except` on the money path is not honest — the rule says *at minimum log a warning*, which is one line per site, and a desk that swallows an order-row or account-summary failure is lying about its own state. Fix them.

**A site-level allow marker instead of a checker-side allowlist.** Some `except` sites are legitimately silent (best-effort cleanup, optional telemetry). Those get `# maintainer: allow-swallow <reason>` on the `except` line. The reason is written where the next reader looks, and the checker honors the marker. An allowlist in `tools/` would drift exactly the way `BASELINE_OVER_LIMIT` already has (it is an empty dict today).

**Remove the §2.3 table rather than fix it.** A table of current line counts is a fossil the moment it merges. Replace it with the command that prints the truth.

**Three PRs, not one.** PR 1 is pure tooling and safe on its own. PR 2 changes product code and must be reviewed as such. PR 3 changes the constitution and should be readable in one diff by an operator who never opens the tooling. One PR would put a `logger.warning` in `ibkr/account_summary.py` in the same review as a rewrite of §2 — nobody reads that carefully.

**Rejected: retire all size rules and rely on review.** Review is the same agents that let 40 silent excepts in. Machine-checked, advisory-visible, blocking on the money path.

**Rejected: put the money-path rules only in `.cursor/rules/`.** Glob-scoped rules load only when an agent edits a matching file. The checker must run on the whole tree in CI so a PR that *adds* a new money-path module is caught.

---

## Task 1 — `maintainer_checks.py`: logical lines, money-path tiers, exemptions, allow marker

**PR:** 1 of 3. Tooling only.

**Files:**

- Modify: `tools/maintainer_checks.py`
- Modify: `tools/test_maintainer_checks.py`
- Create: `tools/test_fixtures/maintainer/entry_point_200_raw_100_logical.tsx` (or build in `tmp_path`; either is fine — `tmp_path` preferred so no fixture rots)

**Interfaces:**

- Consumes: existing `Finding(kind: str, path: str, detail: str, line: int | None, baseline: bool)` at `tools/maintainer_checks.py:145`; `check_file_sizes(files: list[Path]) -> list[Finding]` at `:202`; `HARD_LIMIT_FILES: dict[str, int]` at `:43`; `BASELINE_OVER_LIMIT` / `BASELINE_ACCEPTED_LINES` at `:40-41` (both empty today); `count_lines(path)`; the three producers at `:334` (`swallowed_exception`), `:359` (`except_return_empty`), `:380` (`empty_promise_catch`); `run_checks() -> dict` at `:434` returning `{"findings": [...], "files_scanned": int, "css_line_counts": {...}}`; `main(argv)` at `:486` with `--json` and `--fail-on-kind` (repeatable).
- Produces:
  - `count_logical_lines(path: Path) -> int` — lines that are not blank, not `import`/`from … import` (Python) or `import …` (TS/TSX), and not inside a `/* */`, `{/* */}`, `"""` block or starting with `//`, `#`, `*`. Deterministic, no AST.
  - `ENTRY_POINT_LOGICAL_LIMIT = 150` (new constant). `HARD_LIMIT_FILES` for `backend/main.py` and `frontend/src/App.tsx` switches to logical lines; `frontend/src/index.css` keeps its raw import-only limit of 50 (unchanged).
  - `MONEY_PATH_PREFIXES: tuple[str, ...] = ("backend/execution/", "backend/ibkr/", "backend/nova_os/", "backend/sim/", "backend/hod_momo")` and `_is_money_path(rel: str) -> bool`. **Operator decision O1** below on the exact list; ship with this default.
  - New kinds: `file_size_money`, `swallowed_exception_money`, `except_return_empty_money`. Emitted *instead of* the generic kind when `_is_money_path(rel)`. `empty_promise_catch` is frontend-only and has no money variant.
  - `GENERIC_SIZE_EXEMPT_PATTERNS = ("backend/constants_", "frontend/src/constantGroups/")` — generic `file_size` is not emitted for these. CSS keeps `DOMAIN_CSS_LIMIT = 1000` (already separate). Tests are already skipped by `_is_test_path`.
  - `BASELINE_OVER_LIMIT` populated with the money-path files over 400 today, at their current counts (implementer re-runs the checker; expected set on `b92b9ad`: `backend/ibkr/discovery.py` 714, `backend/hod_momo_active.py` 518, `backend/ibkr/client.py` 453, `backend/ibkr/scanner_stream.py` 423, `backend/hod_momo_trade.py` 411, `backend/execution/service.py` 404, `backend/ibkr/account.py` 402). `file_size_money` fires for an unbaselined money-path file > 400 **or** a baselined one that exceeds its accepted count. The existing `file_size_baseline` kind is retired in favour of `file_size_money` for these entries (keep the kind name reachable for one release if any test references it; grep first).
  - Allow marker: an `except` line (Python) or `catch` line (TS) carrying `# maintainer: allow-swallow <reason>` / `// maintainer: allow-swallow <reason>` with a non-empty reason suppresses the swallowed/empty finding for that site. A marker with an empty reason is itself a finding, kind `allow_marker_missing_reason`.
  - `run_checks()` result gains `"logical_line_counts": {rel: int}` for the two entry points so the PR body and #393 can quote them.

**Steps:**

- [ ] Write failing tests in `tools/test_maintainer_checks.py` (all use `tmp_path` and monkeypatch `REPO_ROOT` the way the existing tests do — read the top of that file first):
  - `test_count_logical_lines_skips_imports_comments_blank` — a `.py` and a `.tsx` sample with known counts; assert exact integers.
  - `test_entry_point_uses_logical_lines` — an `App.tsx`-shaped file with 200 raw / 100 logical lines under `frontend/src/` → no `file_size_hard`; the same with 160 logical → one `file_size_hard` whose `detail` reads `"160 logical lines > entry-point limit 150 (N raw)"`.
  - `test_money_path_kinds` — `backend/execution/x.py` with `except Exception: pass` → `swallowed_exception_money`; the same file under `backend/news/` → `swallowed_exception`.
  - `test_constants_exempt_from_generic_size` — `backend/constants_x.py` with 500 lines → no `file_size`; `backend/foo.py` with 500 lines → one `file_size`.
  - `test_money_path_size_baseline_growth` — a baselined money-path file at its accepted count → no finding; +1 line → `file_size_money`; an unbaselined money-path file at 401 → `file_size_money`.
  - `test_allow_swallow_marker` — marker with reason suppresses; marker without reason → `allow_marker_missing_reason`.
- [ ] Run: `python3 -m pytest tools/test_maintainer_checks.py -q` → **must fail** on the six new tests (and only those).
- [ ] Implement in `tools/maintainer_checks.py`. Keep the file's existing structure; add helpers next to `count_lines`. Do **not** grow the file past its current 522 lines — it is itself a `file_size` finding. Move `count_lines`, `count_logical_lines`, the money-path helpers and the exemption constants into a new `tools/maintainer_lib/sizes.py` (there is already a `maintainer_lib/` package with `deps.py` and `ib_loop.py`; follow their import style). Net effect: `maintainer_checks.py` shrinks.
- [ ] Run: `python3 -m pytest tools/test_maintainer_checks.py -q` → all pass, including the pre-existing `test_run_checks_on_real_repo_reports_index_css`, which currently fails on master because of `App.tsx` (that is #393's symptom; it passes once logical lines are in).
- [ ] Run the checker on the real tree and record the output in the PR body: `python3 tools/maintainer_checks.py --json | python3 -c "import json,sys,collections; d=json.load(sys.stdin); print(collections.Counter(f['kind'] for f in d['findings'])); print(d['logical_line_counts'])"`. Expected on `b92b9ad` + this task: `file_size_hard` **0**; `file_size` **≈12** (22 today, minus the 3 constants modules now exempt, minus the 7 money-path files now baselined; the 1154-line stylesheet stays as a legitimate CSS finding); `file_size_money` **0** (all 7 are baselined at their current counts); `swallowed_exception_money` + `except_return_empty_money` **18**; `logical_line_counts` shows `frontend/src/App.tsx` **100**, `backend/main.py` **≤ 40**.

**Verify:** `python3 -m pytest tools/test_maintainer_checks.py -q && python3 tools/maintainer_checks.py --fail-on-kind ib_loop_sync_io --fail-on-kind file_size_hard; echo exit=$?` → tests pass, `exit=0`.

---

## Task 2 — CI runs the checker's test file and reports every kind

**PR:** 1 of 3 (same PR as Task 1).

**Files:**

- Modify: `.github/workflows/deploy.yml` (two places: the tools pytest list at `:232`, and the maintainer step at `:245`)
- Create: `tools/test_deploy_workflow_maintainer.py` (there is precedent for asserting on workflow YAML in `tools/test_desktop_pack_workflow.py` and `tools/test_pr_delivery_workflow.py`; copy their loader)

**Interfaces:**

- Consumes: `deploy.yml` job `agent-contract` (the job that already runs `maintainer_checks.py`).
- Produces: the tools pytest list includes `tools/test_maintainer_checks.py` and `tools/test_deploy_workflow_maintainer.py`; the maintainer step becomes two steps:
  1. `Maintainer report (advisory)` — `python tools/maintainer_checks.py --json > maintainer.json` then a `python -c` one-liner that prints the kind counter to the job log, `continue-on-error: true`. This is what makes every kind *visible* without blocking.
  2. `Maintainer gate` — `python tools/maintainer_checks.py --fail-on-kind ib_loop_sync_io --fail-on-kind file_size_hard`. PR 2 appends the three `_money` kinds here.

**Steps:**

- [ ] Write `tools/test_deploy_workflow_maintainer.py` asserting: (a) the tools pytest step's `run:` string contains `tools/test_maintainer_checks.py`; (b) a step exists whose `run:` contains `--fail-on-kind file_size_hard`; (c) a step exists with `continue-on-error: true` whose `run:` contains `maintainer_checks.py --json`.
- [ ] Run: `python3 -m pytest tools/test_deploy_workflow_maintainer.py -q` → **must fail** (3 assertions).
- [ ] Edit `deploy.yml` as above. Keep the `ci-scope` gating that already wraps this job; do not change `if:` conditions.
- [ ] Run: `python3 -m pytest tools/test_deploy_workflow_maintainer.py tools/test_ci_scope_workflows.py -q` → pass. The second file guards CR characters and scope gating in workflow files; it must still pass.

**Verify:** `python3 -m pytest tools/test_deploy_workflow_maintainer.py tools/test_ci_scope_workflows.py tools/test_maintainer_checks.py -q` → all pass. Then open PR 1 and paste the CI job log's kind counter into the PR body.

**PR 1 body:** Refs #393 (not Closes — §2.3 is still wrong until PR 3). Verified by: the three pytest commands above plus the real-tree kind counter.

---

## Task 3 — Fix the 18 money-path silent `except` sites, then make the `_money` kinds blocking

**PR:** 2 of 3. Product code. Review this one as a trading-desk change, not a lint change.

**Files (Modify — exact sites on `b92b9ad`; re-run the checker first, the line numbers move):**

| File | Line | Kind today |
|---|---|---|
| `backend/hod_momo_session.py` | 34 | swallowed |
| `backend/sim/market.py` | 119 | swallowed |
| `backend/sim/market.py` | 204 | swallowed |
| `backend/sim/market.py` | 289 | swallowed |
| `backend/ibkr/gapper_view.py` | 103 | swallowed |
| `backend/ibkr/scanner_stream.py` | 296 | swallowed |
| `backend/ibkr/scanner_session.py` | 246 | swallowed |
| `backend/ibkr/order_rows.py` | 57 | swallowed |
| `backend/ibkr/account_marks.py` | 52 | swallowed |
| `backend/ibkr/account_marks.py` | 98 | swallowed |
| `backend/ibkr/account_kind.py` | 86 | swallowed |
| `backend/ibkr/tape_stream.py` | 381 | swallowed |
| `backend/ibkr/account_summary.py` | 96 | swallowed |
| `backend/ibkr/account_summary.py` | 102 | swallowed |
| `backend/ibkr/gateway_trail.py` | 82 | swallowed |
| `backend/ibkr/depth/state.py` | 199 | swallowed |
| `backend/execution/store_facts.py` | 230 | swallowed / returns empty |
| `backend/execution/startup_sweep.py` | 100 | swallowed / returns empty |

- Modify: `.github/workflows/deploy.yml` — append `--fail-on-kind swallowed_exception_money --fail-on-kind except_return_empty_money --fail-on-kind file_size_money` to the `Maintainer gate` step. **Last commit of the PR**, after every site is green.
- Modify: `tools/test_deploy_workflow_maintainer.py` — assert the three kinds are in the gate step.
- Test: one regression test per site **where the fix changes observable behavior** (e.g. a function that used to return `{}` now returns `{}` *and* logs). Where the only change is an added `logger.warning`, a `caplog` assertion in the module's existing test file is enough. Where the site is legitimately silent and gets a marker, no test.

**Interfaces:**

- Consumes: `logging.getLogger(__name__)` (already the convention, §6.3).
- Produces: nothing new. Return values and raised exceptions are **unchanged** at every site. This task adds logging and markers only.

**Steps, per site (do them one file at a time, one commit per file):**

- [ ] Read the `try` body and the `except`. Decide one of three:
  - **(a) Log it.** The failure means the desk is missing data it would otherwise show (account summary, order rows, marks, depth state, gateway trail, scanner stream). Add `logger.warning("<what failed> for %s: %s", <symbol/ctx>, exc, exc_info=False)` inside the `except`. Change `except Exception:` to `except Exception as exc:`. Keep the same fallthrough.
  - **(b) Log at debug + marker.** The failure is expected and frequent (e.g. a tick that arrives before a contract is qualified) and a warning would spam `backend/logs/`. Use `logger.debug(...)` **and** add `# maintainer: allow-swallow expected-before-<condition>`. The marker forces a written reason; the debug line keeps it observable when someone turns the level up.
  - **(c) Marker only.** Genuinely best-effort with no state impact (e.g. closing a handle that may already be closed). `# maintainer: allow-swallow best-effort-cleanup`. Expect this to be rare on this list — argue for it in the commit message.
- [ ] Run the module's existing tests: `python3 -m pytest backend/tests/test_<module>*.py -q` → pass.
- [ ] Run the checker on that file: `python3 tools/maintainer_checks.py --json | python3 -c "import json,sys; [print(f) for f in json.load(sys.stdin)['findings'] if f['path']=='<file>' and f['kind'].endswith('_money')]"` → prints nothing.
- [ ] After all 18: run the full backend suite once: `cd backend && python3 -m pytest -q` → same pass count as master (978+ on 2026-09-20), zero new failures.
- [ ] Flip CI: add the three kinds to the gate step; update the workflow test; run it.

**Verify:** `python3 tools/maintainer_checks.py --fail-on-kind ib_loop_sync_io --fail-on-kind file_size_hard --fail-on-kind swallowed_exception_money --fail-on-kind except_return_empty_money --fail-on-kind file_size_money; echo exit=$?` → `exit=0`. Paste the per-site decision (a/b/c) table into the PR body.

**PR 2 body:** Refs #393. No issue closes. State plainly: "18 sites, N logged at warning, M at debug with marker, K marker-only; no return value or exception changed." Verified by the full backend suite count.

---

## Task 4 — Rewrite `AGENTS.md` §2 as behavior rules

**PR:** 3 of 3. Constitution. Bundle Tasks 4–7 in one PR so the operator reads the whole rule change in one diff.

**Files:**

- Modify: `AGENTS.md` lines 61–162 (§2 header through the end of §2.4). §2.4 is kept **verbatim**; only §2.1–§2.3 are replaced.

**Interfaces:** none (text).

**Replacement text for §2.1–§2.3** (paste exactly; §2.4 follows unchanged):

```markdown
## 2. 📐 Modularity Laws (Enforced by `tools/maintainer_checks.py`)

These are rules about behavior, not snapshots of the tree. No file list is
maintained here; the tree is the truth and the checker is the gate.

### 2.1 Entry points hold wiring only

`backend/main.py` and `frontend/src/App.tsx` contain app creation, providers,
middleware, lifespan hooks and route/page registration. Nothing else. The
checker enforces **≤ 150 logical lines** (imports, comments and blank lines
are not counted). CI kind: `file_size_hard`, blocking.

Current counts: `python3 tools/maintainer_checks.py --json` → `logical_line_counts`.

### 2.2 Size is a smell everywhere and a blocker on the money path

The **money path** is every module under `backend/execution/`, `backend/ibkr/`,
`backend/nova_os/`, `backend/sim/` and `backend/hod_momo*`. (List:
`MONEY_PATH_PREFIXES` in `tools/maintainer_lib/sizes.py`.)

- Money path: a new module over **400 lines** blocks CI (`file_size_money`).
  Modules already over the limit are baselined at their current size and may
  not grow; splitting them is backlog work, not linter work.
- Everywhere else: over 400 lines (Python, `.ts`) or 300 lines (`.tsx`) is an
  advisory finding (`file_size`). Constants modules (`backend/constants_*.py`,
  `frontend/src/constantGroups/`) and stylesheets (own limit, 1000) are exempt.

### 2.3 The money path never swallows

On the money path, an `except` that neither re-raises nor logs is a CI failure
(`swallowed_exception_money`, `except_return_empty_money`). At minimum log a
warning with the symbol or context and the exception. A site that must stay
silent carries `# maintainer: allow-swallow <reason>` on the `except` line;
an empty reason is itself a finding. Elsewhere the same patterns are advisory.
```

**Steps:**

- [ ] Replace the block. Confirm §2.4 "Refactoring Protocol" is byte-identical before and after (`git diff` shows no hunk inside it).
- [ ] Add a maintenance-log row at the top of §11's table:

  `| 2026-09-20 | §2 rewritten from file lists and raw line counts to behavior rules: entry points ≤150 logical lines; money-path modules (execution/ibkr/nova_os/sim/hod_momo) block on size and on silent except; everything else advisory. §2.3 table removed — the checker prints the truth. §3 contracts moved to architecture/contracts/. Invariant #1 points there; invariant #5 narrowed to posture and structure. Closes #393. Plan: docs/plans/2026-09-20-code-rules-rewrite.md. | User Directive + Claude Code |`

- [ ] Update the §2.3 row in §10 "Compliance Audit" if any text there references the old table (grep `App.tsx` in §10; on `b92b9ad` §10 says "No open constitution compliance rows" — leave it).

**Verify:** `python3 tools/doc_invariants.py; echo exit=$?` → `OK`, `exit=0`. `grep -c 'GapperTable\|<150 lines\|73 lines' AGENTS.md` → `0`.

---

## Task 5 — Move §3 contracts out; reword invariants #1 and #5

**PR:** 3 of 3.

**Files:**

- Create: `architecture/contracts/README.md` — one paragraph: "Response and command contracts confirmed before the code that serves them (AGENTS.md invariant #1). One file per surface. Keep JSON examples runnable; keep prose to what a cold agent would get wrong."
- Create: `architecture/contracts/ci-scope.md` ← §3 "CI scope output"
- Create: `architecture/contracts/capture-replay.md` ← §3 "Capture / replay truth" + "Replay progress and capture fidelity" + the "Capture market projections" paragraph
- Create: `architecture/contracts/scanner-payloads.md` ← §3 "Input Payload (Raw)" + "Output / Delivery Payload"
- Create: `architecture/contracts/execution-command.md` ← §3 "Execution command (ADR 007)"
- Modify: `AGENTS.md` §3 becomes three lines: heading, "Contracts live in `architecture/contracts/` — one file per surface. Confirm the contract there before writing the tool or endpoint (Invariant #1).", and a bullet list linking the four files.
- Modify: `AGENTS.md` §1 row 1 (Data-First): "No tool or endpoint is written before its contract is confirmed in `architecture/contracts/`."
- Modify: `AGENTS.md` §1 row 5 (SOP before code): "If **trading posture or a safety gate** changes, update the live docs first (`doc-invariants.mdc` gates this). If **structure** moves, cite or write an ADR first (`architecture/README.md`). For every other change the PR body's *Why this approach* is the SOP; do not edit this file or `.cursor/rules/` for ordinary features."
- Modify: `tools/doc_invariants.py` **only if** any entry in its `INVARIANTS` tuple (line 50) matches text that moved out of §3. Read the tuple before moving; if a pattern targets `AGENTS.md` for a §3 phrase, point it at the new contract file. Update `tools/test_doc_invariants.py` accordingly.
- Modify: `architecture/README.md` — add `contracts/` to its directory description.

**Interfaces:** none (text). `doc_invariants.py` is the only consumer that might key on §3 text.

**Steps:**

- [ ] `grep -n 'contracts\|Capture / replay\|execution command\|CI scope' tools/doc_invariants.py` — note any hit.
- [ ] Move the text with `git mv`-like fidelity: copy verbatim, then delete from `AGENTS.md`. Do not rewrite the contracts while moving them — that is a separate change and would hide in this diff.
- [ ] Reword invariants #1 and #5 as above.
- [ ] Run: `python3 tools/doc_invariants.py` → if it fails, fix the pattern target (step 1 told you which). Run `python3 -m pytest tools/test_doc_invariants.py -q`.

**Verify:** `python3 tools/doc_invariants.py && python3 -m pytest tools/test_doc_invariants.py -q; echo exit=$?` → `exit=0`. `wc -c AGENTS.md` → at least 4,000 bytes smaller than on `b92b9ad` (53,226).

---

## Task 6 — Sync the glob-scoped rules to the new text

**PR:** 3 of 3.

**Files (Modify):**

- `.cursor/rules/file-size-limits.mdc` — replace its numbers with the §2.1/§2.2 text (logical lines, money path, exemptions). Keep it glob-scoped.
- `.cursor/rules/backend-modularity.mdc` — remove the module list (3 stale hits); keep "no logic in `main.py`" and point at §2.1. Add one line: "Money-path modules (§2.2) block on size and silent except."
- `.cursor/rules/frontend-modularity.mdc` — remove the component/hook list (2 stale hits); keep "no logic in `App.tsx`" and point at §2.1.
- `.cursor/rules/constitution.mdc` — 2 hits on old numbers; update the "common violations" line to the new kinds.
- `.cursor/rules/centralized-constants.mdc` — 1 hit; note that constants modules are exempt from generic size findings and why (a table is not complexity).
- Check and leave alone unless they quote a number: `karpathy-guidelines.mdc`, `single-market-data-feed.mdc`, `ai-news-digest.mdc` (1 hit each on `b92b9ad`; likely incidental "400 lines" prose — read before touching).

**Interfaces:** none. `tools/agent_contract.py --ci` validates rule frontmatter; it must still pass.

**Steps:**

- [ ] `grep -nE 'GapperTable|scanner\.py|<150|<200|150 lines|200 lines|400 lines' .cursor/rules/*.mdc` → edit every hit listed above.
- [ ] Run: `python3 tools/agent_contract.py --ci` → PASS.
- [ ] Run: `python3 tools/engineering_skills_audit.py` → PASS, 0 findings (it checks the always-on MDC set is intact).

**Verify:** `grep -cE 'GapperTable|scanner\.py|<150 lines|<200 lines' .cursor/rules/*.mdc | grep -v ':0$'; echo "(empty = clean)"` → empty.

---

## Task 7 — Close #393 and file the split issues

**PR:** 3 of 3 (body), plus GitHub metadata.

**Files:** none.

**Steps:**

- [ ] PR 3 body: `Closes #393`. In *Verified by*, quote `logical_line_counts` from the checker (Task 1) and the CI job log showing `file_size_hard` in the gate step (Task 2). All three of #393's acceptance criteria are met by this point: entry point under its (logical) limit, §2.3 no longer asserts a false count, CI reports a future breach.
- [ ] Open one `deferred` issue per baselined money-path module that is a real split candidate (not for the linter's sake — because they are the largest logic files on the order/feed path): `backend/ibkr/discovery.py` (714) and `backend/hod_momo_active.py` (518). Labels: `deferred`, `P3`, `enhancement`, `domain:ibkr` / `domain:hod-momo`. Body fields per §7.2c. Link them from PR 3 as `Refs`. Do **not** open issues for the five at 402–453; they are within a normal refactor of the next PR that touches them (§2.4 still applies).
- [ ] Attach PR 3 to Nova Delivery (`tools/nova_delivery_project.py add --url <pr>`) when the token allows; on 403, say so in the PR body.
- [ ] After merge: confirm the head branch is gone (`git fetch --prune && python3 tools/stale_pr_branches.py`).

**Verify:** #393 shows *Closed by* PR 3. `python3 tools/backlog_triage.py check` (or the CI weekly sweep) reports the two new issues in `00 - Untriaged` with all four label groups present.

---

## Operator decisions (record on the PR or on #393 — do not guess)

- **O1 — Money-path list.** Proposed: `backend/execution/`, `backend/ibkr/`, `backend/nova_os/`, `backend/sim/`, `backend/hod_momo*`. Arguments for adding `backend/archive/` (capture is the replay truth source) and `backend/journal/` (R-multiple facts). Arguments against: they do not place orders or paint live account state. Ship with the proposed five; widen by editing one tuple.
- **O2 — Does generic `file_size` ever become blocking?** This plan says no: outside the money path a big file is a review conversation, not a gate. If the operator wants a date, add it to the maintenance-log row.
- **O3 — Fix or baseline the 18?** This plan fixes them (Task 3) on the grounds that "at minimum log a warning" is one line per site and the sites are order rows, account summary and depth state. If the operator prefers to baseline and fix later, Task 3 collapses to "add the 18 markers with reason `baseline-2026-09-20`" and a `P2` issue to remove them; the CI flip still happens.

## Out of scope (deliberately)

- **Process-rule audit** (always-on rule volume, dormant subagents, graphify hooks, next-move footer, Windows-only `py -3` in rules, draft-vs-ready PR conflict with cloud harnesses). Separate plan; different reviewers; nothing in this plan depends on it.
- **The 48 `cross_feature_import` findings.** They need a pass against `architecture/dependency-rules.md` with its own baseline decision. Leave the kind advisory.
- **Splitting the baselined modules.** Two issues are filed (Task 7); the work is backlog.
- **`tools/repo_hygiene.py stop-gate` false positives.** Observed this session: a fresh clone whose `origin/master` ref was 56 commits stale tripped the gate on every turn until `git fetch origin master`. The gate should fetch (or compare to `@{upstream}`) before counting. One-line fix, own issue.

## Rollback

- PR 1: revert restores the old checker and the single-kind CI step. No product code involved.
- PR 2: revert removes 18 log lines and 3 CI kinds. Return values were never changed, so nothing downstream moves.
- PR 3: revert restores the old §2/§3 text and rule files. The tooling from PR 1 keeps running; the constitution would be temporarily behind the checker, which is the state it is in today.
