"""Lazy access to ``scan_runners`` facade for monkeypatch-friendly deps."""


def facade():
    import scan_runners as sr
    return sr
