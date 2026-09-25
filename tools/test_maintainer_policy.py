"""The code-shape policy the maintainer gate enforces (AGENTS.md §2, §6.3).

Size: a soft limit that asks for a reason, a ceiling that blocks, growth judged
against a base. Silent failures: CI-failing on the money path, a reason at the
site otherwise. Feature imports: resolved paths, frozen counts. Ownership:
every backend package and frontend folder says what it owns.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from maintainer_lib import baselines, owners, size_policy, swallow  # noqa: E402
from maintainer_lib.deps import deep_import_target  # noqa: E402
from maintainer_lib.gate import GATE_KINDS  # noqa: E402
from test_maintainer_checks import _load_module  # noqa: E402


@pytest.fixture(scope="module")
def mc():
    return _load_module()


def _body(n: int) -> str:
    return "".join(f"x{i} = {i}\n" for i in range(n))


def _sizes(files, rel_of, base_lines=None, mc_mod=None):
    finding = mc_mod.Finding
    return size_policy.check_file_sizes(
        files, lambda p: rel_of[p], finding, {}, lambda p: False, base_lines
    )


# --- size -------------------------------------------------------------------


def test_soft_limit_is_advisory_and_a_reason_clears_it(mc, tmp_path: Path):
    plain = tmp_path / "a.py"
    plain.write_text(_body(450), encoding="utf-8")
    marked = tmp_path / "b.py"
    marked.write_text(
        "# maintainer: one-concern one audited scanner-slot invariant\n" + _body(450),
        encoding="utf-8",
    )
    empty = tmp_path / "c.py"
    empty.write_text("# maintainer: one-concern\n" + _body(450), encoding="utf-8")
    rel = {plain: "backend/a.py", marked: "backend/b.py", empty: "backend/c.py"}
    kinds = {(f.path, f.kind) for f in _sizes([plain, marked, empty], rel, mc_mod=mc)}
    assert kinds == {("backend/a.py", "file_size"), ("backend/c.py", "one_concern_no_reason")}


def test_nothing_passes_the_ceiling_not_even_with_a_reason_or_as_data(mc, tmp_path: Path):
    marked = tmp_path / "big.py"
    marked.write_text("# maintainer: one-concern a long but single concern here\n" + _body(900),
                      encoding="utf-8")
    table = tmp_path / "constants_x.py"
    table.write_text(_body(900), encoding="utf-8")
    rel = {marked: "backend/big.py", table: "backend/constants_x.py"}
    kinds = sorted(f.kind for f in _sizes([marked, table], rel, mc_mod=mc))
    assert kinds == ["file_size_ceiling", "file_size_ceiling"]


def test_constants_tables_and_components_under_400_are_not_flagged(mc, tmp_path: Path):
    table = tmp_path / "market_ui.ts"
    table.write_text(_body(600), encoding="utf-8")
    component = tmp_path / "Panel.tsx"
    component.write_text(_body(350), encoding="utf-8")  # the old 300-line .tsx rule is gone
    rel = {table: "frontend/src/constantGroups/market_ui.ts", component: "frontend/src/x/Panel.tsx"}
    assert _sizes([table, component], rel, mc_mod=mc) == []


@pytest.mark.parametrize(
    ("before", "grows"),
    [(None, True), (390, True), (440, True), (450, False), (500, False)],
)
def test_growth_past_the_soft_limit_needs_a_reason(mc, tmp_path: Path, before, grows):
    path = tmp_path / "engine.py"
    path.write_text(_body(450), encoding="utf-8")
    found = _sizes([path], {path: "backend/engine.py"}, lambda rel: before, mc_mod=mc)
    kinds = [f.kind for f in found]
    assert kinds == (["file_size", "file_size_growth"] if grows else ["file_size"])


def test_a_marked_file_may_grow(mc, tmp_path: Path):
    path = tmp_path / "engine.py"
    path.write_text("# maintainer: one-concern the one audited order-safety decision\n" + _body(450),
                    encoding="utf-8")
    assert _sizes([path], {path: "backend/engine.py"}, lambda rel: 300, mc_mod=mc) == []


def test_an_unknown_base_is_reported_not_silently_skipped(mc):
    report = mc.run_checks(base="no-such-ref-for-maintainer-tests")
    assert report["size_base"] is None
    assert any(f["kind"] == "size_base_unavailable" for f in report["findings"])


# --- silent failures ---------------------------------------------------------


def _swallow(tmp_path: Path, rel: str, text: str, mc_mod) -> list:
    path = tmp_path / Path(rel).name
    path.write_text(text, encoding="utf-8")
    return swallow.check_swallowed_errors([path], lambda p: rel, mc_mod.Finding, lambda p: False)


def test_money_path_silence_gets_its_own_kind(mc, tmp_path: Path):
    text = "try:\n    x()\nexcept Exception:\n    pass\n"
    assert [f.kind for f in _swallow(tmp_path, "backend/execution/x.py", text, mc)] == [
        "swallowed_exception_money"
    ]
    assert [f.kind for f in _swallow(tmp_path, "backend/news/x.py", text, mc)] == [
        "swallowed_exception"
    ]


def test_a_header_comment_or_dotted_name_no_longer_hides_a_site(mc, tmp_path: Path):
    text = (
        "try:\n    x()\nexcept asyncio.TimeoutError:  # expected\n    pass\n"
        "try:\n    y()\nexcept (A, B) as exc:\n    # quiet\n    pass\n"
    )
    found = _swallow(tmp_path, "backend/ibkr/x.py", text, mc)
    assert [f.line for f in found] == [3, 7]


def test_a_site_reason_clears_it_and_an_empty_one_is_a_finding(mc, tmp_path: Path):
    ok = "try:\n    x()\nexcept ValueError:  # maintainer: allow-swallow the next format is tried below\n    pass\n"
    bad = "try:\n    x()\nexcept ValueError:  # maintainer: allow-swallow ok\n    pass\n"
    assert _swallow(tmp_path, "backend/ibkr/a.py", ok, mc) == []
    assert [f.kind for f in _swallow(tmp_path, "backend/ibkr/b.py", bad, mc)] == [
        "allow_swallow_no_reason"
    ]


def test_file_allowlists_never_apply_on_the_money_path(mc, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(swallow, "EXCEPT_RETURN_EMPTY_ALLOWLIST", {"backend/ibkr/x.py", "backend/y.py"})
    text = "def f():\n    try:\n        x()\n    except Exception:\n        return []\n"
    assert [f.kind for f in _swallow(tmp_path, "backend/ibkr/x.py", text, mc)] == [
        "except_return_empty_money"
    ]
    assert _swallow(tmp_path, "backend/y.py", text, mc) == []


# --- feature imports and the ratchet ------------------------------------------


@pytest.mark.parametrize(
    ("rel", "spec", "target"),
    [
        ("frontend/src/ibkr/x.ts", "../chart/barsStore", "chart"),
        ("frontend/src/ibkr/x.ts", "@/chart/barsStore", "chart"),
        ("frontend/src/ibkr/x.ts", "../chart", None),         # the public barrel
        ("frontend/src/ibkr/x.ts", "../chart/index", None),
        ("frontend/src/ibkr/sub/x.ts", "../chart/y", "ibkr"),  # a sibling folder, not the slice
        ("frontend/src/ibkr/x.ts", "../components/ui/button", None),
        ("frontend/src/ibkr/x.ts", "./local", None),
    ],
)
def test_deep_imports_are_resolved_before_they_are_judged(rel, spec, target):
    assert deep_import_target(rel, spec, ("chart", "ibkr")) == target


def test_the_ratchet_freezes_counts_not_line_numbers(mc):
    finding = mc.Finding
    rows = [finding(kind="cross_feature_import", path="frontend/src/a/x.ts",
                    detail="a imports internals of b", line=n) for n in (3, 9)]
    frozen = {"cross_feature_import": {"frontend/src/a/x.ts|a imports internals of b": 1}}
    assert baselines.apply_baseline_counts(rows, frozen) == []
    assert [r.baseline for r in rows] == [True, False]
    stale = baselines.apply_baseline_counts(
        rows, {"cross_feature_import": {"frontend/src/a/x.ts|a imports internals of b": 3}}
    )
    assert stale == [("cross_feature_import", "frontend/src/a/x.ts|a imports internals of b", 3, 2)]


def test_baselines_refuse_an_unknown_version(tmp_path: Path):
    path = tmp_path / "baselines.json"
    path.write_text(json.dumps({"schema_version": 99, "counts": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        baselines.load_counts(path)
    path.write_text(json.dumps({"schema_version": 1, "fingerprints": []}), encoding="utf-8")
    assert baselines.load_counts(path) == {}


# --- ownership ----------------------------------------------------------------


def test_every_package_and_folder_must_say_what_it_owns(mc, tmp_path: Path):
    root = tmp_path / "repo"
    (root / "backend" / "good").mkdir(parents=True)
    (root / "backend" / "good" / "__init__.py").write_text('"""Owns the good things."""\n', encoding="utf-8")
    (root / "backend" / "bare").mkdir()
    (root / "backend" / "bare" / "__init__.py").write_text("# a comment is not a docstring\n", encoding="utf-8")
    src = root / "frontend" / "src"
    for folder in ("chart", "newthing"):
        (src / folder).mkdir(parents=True)
        (src / folder / "a.ts").write_text("export {};\n", encoding="utf-8")
    (src / "FOLDERS.md").write_text(
        "| Folder | Kind | Owns |\n|---|---|---|\n"
        "| `chart/` | feature | The chart. |\n| `gone/` | shared | Removed. |\n",
        encoding="utf-8",
    )
    found = {(f.kind, f.path) for f in owners.check_owners(root, mc.Finding)}
    assert found == {
        ("package_owner_missing", "backend/bare/__init__.py"),
        ("folder_owner_missing", "frontend/src/newthing/"),
        ("folder_owner_stale", "frontend/src/FOLDERS.md"),
    }
    assert owners.feature_folders(root) == ("chart",)


def test_module_map_reads_the_statements_from_the_code():
    import module_map

    text = module_map.render(owners.module_map(REPO_ROOT))
    assert "| `backend/execution/` |" in text
    assert "| `frontend/src/ibkr/` | feature |" in text


# --- the real tree ----------------------------------------------------------------


# The lint has its own CI steps: Backend tests' Ruff, and the Maintainer gate. Counting it here
# too would report one finding twice, and fail the tool tests wherever ruff is not installed
# (AGENTS.md §6.7).
LINT_KINDS = {"ruff", "ruff_unavailable", "ruff_error"}


def test_the_real_tree_passes_the_gate(mc):
    report = mc.run_checks()
    blocking = [f for f in report["findings"]
                if f["kind"] in GATE_KINDS and f["kind"] not in LINT_KINDS and not f["baseline"]]
    assert blocking == [], blocking


def test_the_lint_kinds_left_out_above_are_the_gates_lint_kinds():
    assert LINT_KINDS <= set(GATE_KINDS)
    assert {kind for kind in GATE_KINDS if kind.startswith("ruff")} == LINT_KINDS


def test_the_frozen_counts_match_the_tree(mc):
    report = mc.run_checks()
    stale = [f for f in report["findings"] if f["kind"] == "baseline_stale"]
    assert stale == [], "run `py -3 tools/maintainer_checks.py --update-baselines`"


def test_the_checker_obeys_its_own_soft_limit(mc):
    for rel in ("tools/maintainer_checks.py", *(
        f"tools/maintainer_lib/{p.name}" for p in (REPO_ROOT / "tools" / "maintainer_lib").glob("*.py")
    )):
        assert size_policy.count_lines(REPO_ROOT / rel) <= size_policy.SOFT_LIMIT, rel
