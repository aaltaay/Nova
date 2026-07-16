"""Nova security audit runner.

Side-effect-free by default.  Use --write-registry to persist findings.

Usage
-----
  py -3 tools/security_audit.py                          # human report
  py -3 tools/security_audit.py --json                   # JSON report
  py -3 tools/security_audit.py --json --write-registry  # merge + persist
  py -3 tools/security_audit.py --fail-on-findings       # exit 1 for new critical

Run from repo root.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root and tools/ are importable regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "tools"))

from tools.security_lib.checks import detect_tools, run_builtin_checks
from tools.security_lib.registry import (
    REGISTRY_PATH,
    load_registry,
    merge_findings,
)


def _count_by_severity(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def _new_critical_open(registry: dict, new_ids: list[str]) -> list[dict]:
    """Return new findings that are critical and still open."""
    id_set = set(new_ids)
    return [
        f
        for f in registry.get("findings", [])
        if f["id"] in id_set
        and f.get("severity") == "critical"
        and f.get("status") == "open"
    ]


def run_audit(write_registry: bool = False) -> dict:
    """Run all checks and return the audit report dict."""
    available_tools, blocked_tools = detect_tools()
    raw_findings = run_builtin_checks()

    registry = load_registry()
    registry, new_ids, updated_ids = merge_findings(
        raw_findings=raw_findings,
        registry=registry,
        tools_run=["nova-builtin"] + available_tools,
        blocked_tools=blocked_tools,
        write=write_registry,
        path=REGISTRY_PATH,
    )

    all_findings = registry.get("findings", [])
    open_findings = [f for f in all_findings if f.get("status") == "open"]
    severity_counts = _count_by_severity(open_findings)

    last_run = registry.get("scan_runs", [{}])[-1] if registry.get("scan_runs") else {}

    return {
        "repo_root": str(_REPO_ROOT),
        "tools_available": available_tools,
        "tools_blocked": blocked_tools,
        "new_finding_ids": new_ids,
        "updated_finding_ids": updated_ids,
        "open_finding_count": len(open_findings),
        "severity_counts": severity_counts,
        "registry_written": write_registry,
        "registry_path": str(REGISTRY_PATH),
        "findings": all_findings,
        "scan_run": last_run,
    }


def print_human(report: dict) -> None:
    print("=" * 60)
    print("Nova Security Audit")
    print("=" * 60)

    if report["tools_blocked"]:
        print(f"\n[BLOCKED] External tools not installed (scan BLOCKED for these):")
        for t in report["tools_blocked"]:
            print(f"  - {t}")
    if report["tools_available"]:
        print(f"\n[OK] External tools available:")
        for t in report["tools_available"]:
            print(f"  - {t}")

    print(f"\nOpen findings: {report['open_finding_count']}")
    sc = report["severity_counts"]
    print(
        f"  critical={sc.get('critical', 0)}  high={sc.get('high', 0)}  "
        f"medium={sc.get('medium', 0)}  low={sc.get('low', 0)}"
    )

    if report["new_finding_ids"]:
        print(f"\nNEW findings this run: {', '.join(report['new_finding_ids'])}")
    if report["updated_finding_ids"]:
        print(f"Updated (last_seen bumped): {', '.join(report['updated_finding_ids'])}")

    print()
    open_findings = [f for f in report["findings"] if f.get("status") == "open"]
    if not open_findings:
        print("No open findings.")
        return

    for f in open_findings:
        sev = f.get("severity", "?").upper()
        fid = f.get("id", "?")
        loc = f.get("location", f.get("path", "?"))
        title = f.get("title", "?")
        print(f"[{sev}] {fid} — {loc}")
        print(f"  {title}")
        if f.get("redacted_evidence"):
            print(f"  evidence: {f['redacted_evidence']}")
        print()

    if report["registry_written"]:
        print(f"Registry written → {report['registry_path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nova security audit runner. Run from repo root.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report to stdout",
    )
    parser.add_argument(
        "--write-registry",
        action="store_true",
        help="Merge findings into security/findings-registry.json",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit 1 if any new critical finding with status=open is found",
    )
    args = parser.parse_args(argv)

    report = run_audit(write_registry=args.write_registry)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        print_human(report)

    if args.fail_on_findings:
        critical_new = _new_critical_open(
            {"findings": report["findings"]}, report["new_finding_ids"]
        )
        if critical_new:
            if not args.json:
                print(
                    f"FAIL: {len(critical_new)} new critical open finding(s) — "
                    "exit 1 per --fail-on-findings",
                    file=sys.stderr,
                )
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
