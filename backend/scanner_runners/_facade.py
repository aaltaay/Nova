"""Lazy access to ``scan_runners`` facade for monkeypatch-friendly deps.

Facade owner: Phase 8A / close-remediation Phase 4.
Removal criterion: orchestration receives injected ports and no longer needs
a service-locator import of ``scan_runners``.
"""


def facade():
    import scan_runners as sr
    return sr
