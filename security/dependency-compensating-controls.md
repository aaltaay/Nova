# Dependency compensating controls (close remediation Phase 2)

Retrieved: 2026-07-16 via `pip-audit -r backend/requirements.txt`.

## Upgraded

| Package | From | To | Notes |
|---------|------|----|-------|
| `python-dotenv` | 1.1.0 | 1.2.2 | Fixes CVE-2026-28684 |
| `transformers` | 4.57.6 | 5.5.0 | Clears prior transformers CVEs with published fixes |
| `torch` | 2.8.0 | 2.10.0 | Clears CVEs with 2.9–2.10 fix versions |

## Residual (no upstream fix at audit time)

| Package | Finding | Compensating control |
|---------|---------|----------------------|
| `torch` 2.10.0 | PYSEC-2026-139, CVE-2025-3000 | Used only for optional local FinBERT sentiment in `backend/news/sentiment.py`. Lazy-loaded; failures degrade to `unavailable`. Not an unauthenticated remote model-serving surface. Re-audit when PyTorch publishes patches. |

Local machine packages outside `requirements.txt` (e.g. `whisperx`, `torchaudio`) may conflict after upgrades — they are not Nova runtime deps.

Re-run: `py -3 -m pip_audit -r backend/requirements.txt`.
