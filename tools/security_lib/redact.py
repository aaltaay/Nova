"""Secret redaction for evidence snippets.

Side-effect-free: only processes strings, writes nothing.
"""

from __future__ import annotations

import re

# Patterns matched in order; first match wins per token.
_REDACT_PATTERNS: list[re.Pattern[str]] = [
    # Quoted secret assignments: key = "VALUE" / key: "VALUE"
    re.compile(
        r"""(?i)(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token|password|passwd|token)"""
        r"""\s*[=:]\s*['"]([A-Za-z0-9+/=_\-]{8,})['"]"""
    ),
    # AWS access keys
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    # Stripe / generic sk_ keys
    re.compile(r"""(sk[_-](?:live|test)[_-][A-Za-z0-9]{16,})"""),
    # PEM private key content (base64 blob lines)
    re.compile(r"((?:[A-Za-z0-9+/]{40,}={0,2}))"),
    # Generic long hex strings (32+ hex chars that look like tokens)
    re.compile(r"\b([0-9a-f]{32,})\b"),
    # Generic alphanumeric tokens ≥ 24 chars after = or :
    re.compile(r"""(?<=[=:\s'"])([A-Za-z0-9_\-]{24,})(?=['"\s,});\n])"""),
]

# Max chars to keep in evidence snippet.
MAX_EVIDENCE_CHARS = 500


def redact(text: str) -> str:
    """Return *text* with secret-looking values replaced by ***REDACTED***."""
    if not text:
        return text
    result = text
    for pattern in _REDACT_PATTERNS:
        result = pattern.sub(_replace_group, result)
    return result[:MAX_EVIDENCE_CHARS]


def _replace_group(m: re.Match[str]) -> str:
    """Replace the first capture group (the secret value) with ***REDACTED***."""
    full = m.group(0)
    if m.lastindex and m.lastindex >= 1:
        secret = m.group(1)
        return full.replace(secret, "***REDACTED***", 1)
    return "***REDACTED***"
