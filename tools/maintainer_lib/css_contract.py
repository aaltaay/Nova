"""The CSS design contract (ADR 006): feature stylesheets scope their selectors
and read text colour from the Nova tokens, not Tailwind's background token.

Moved out of ``maintainer_checks.py`` on 2026-10-07 so the CLI stays the
wiring and every check lives beside its siblings in ``maintainer_lib``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

# Feature/domain CSS must not use bare element selectors (ADR 006).
BARE_FEATURE_SELECTOR = re.compile(
    r"^(form|label|input(?!\[)|button|table|thead|tbody|th|td|header)\s*[,{]",
    re.MULTILINE,
)
# Domain CSS must not read Tailwind --color-muted as text (collision with bg token).
COLOR_MUTED_AS_TEXT = re.compile(r"color\s*:\s*var\(\s*--color-muted\b")
# Allowed adapter / token sheets for Tailwind semantic vars.
CSS_TOKEN_ADAPTER_PATHS = {
    "frontend/src/styles/tailwind-theme.css",
    "frontend/src/index.css",
}


def check_css_design_contract(
    files: list[Path],
    rel_fn: Callable[[Path], str],
    finding_cls: type,
    generated_fn: Callable[[Path], bool],
) -> list:
    """Reject bare feature selectors and --color-muted used as text (ADR 006)."""
    findings = []
    for path in files:
        if path.suffix != ".css" or generated_fn(path):
            continue
        rel = rel_fn(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rel in CSS_TOKEN_ADAPTER_PATHS:
            continue
        for match in BARE_FEATURE_SELECTOR.finditer(text):
            findings.append(finding_cls(
                kind="bare_css_selector", path=rel,
                detail=f"bare '{match.group(1)}' selector -- scope to a feature class (ADR 006)",
                line=text.count("\n", 0, match.start()) + 1,
            ))
        for match in COLOR_MUTED_AS_TEXT.finditer(text):
            findings.append(finding_cls(
                kind="css_token_collision", path=rel,
                detail="color: var(--color-muted) -- use --nova-text-muted / --text-secondary (ADR 006)",
                line=text.count("\n", 0, match.start()) + 1,
            ))
    return findings
