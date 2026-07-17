# Nova Security Tooling — Local Setup & Usage (Windows)

> **Scope:** Development / triage tools. Never run active/attack modes against live broker connections.  
> **ZAP rule:** Baseline scan only — **NEVER** active scan against IB Gateway or any live endpoint.  
> **Cursor agents:** `security-review` = diff-scoped; `security-sentinel` = full repo posture.

---

## 1. pip-audit (Python dependency CVE scanner)

Already in `backend/requirements-dev.txt`. No extra install needed.

```powershell
# From repo root — scans backend/ production deps
pip-audit -r backend/requirements.txt --progress-spinner off

# Include dev deps too
pip-audit -r backend/requirements-dev.txt --progress-spinner off
```

CI equivalent: `python tools/security_audit.py --json` (runs pip-audit + CVSS scoring).

---

## 2. Semgrep (SAST — static analysis)

```powershell
# Install via pip (Python 3.8+ required)
pip install semgrep

# Run against backend Python
semgrep --config=p/python backend/

# Run against frontend TypeScript
semgrep --config=p/typescript frontend/src/

# Focused: secrets only
semgrep --config=p/secrets .
```

Alternative install (Scoop — faster binary):

```powershell
scoop install semgrep
```

Recommended rulesets for Nova:

- `p/python` — general Python safety
- `p/secrets` — leaked keys / tokens
- `p/typescript` — frontend safety
- `p/owasp-top-ten` — OWASP classification

---

## 3. Gitleaks (secrets in git history)

```powershell
# Install via Scoop
scoop install gitleaks

# Or via Chocolatey
choco install gitleaks

# Scan entire git history (recommended first run)
gitleaks detect --source . --report-format json --report-path .tmp/gitleaks-report.json

# Scan only uncommitted changes
gitleaks protect --staged
```

Important: `.env` files are in `.gitignore` — this confirms no committed secrets, but run anyway
to verify no historical leaks.

---

## 4. OSV-Scanner (Open Source Vulnerabilities)

```powershell
# Download latest binary from https://github.com/google/osv-scanner/releases
# Place osv-scanner.exe in a folder on PATH (e.g. C:\Tools\)

# Scan Python lockfile
osv-scanner --lockfile backend/requirements.txt

# Scan Node lockfile
osv-scanner --lockfile frontend/package-lock.json

# Scan everything
osv-scanner -r .
```

OSV-Scanner cross-references against the OSV database — complements pip-audit which uses PyPI advisories.

---

## 5. Trivy (container + filesystem scanner)

```powershell
# Install via Scoop
scoop install trivy

# Or via Chocolatey
choco install trivy

# Scan filesystem (deps + secrets + misconfigs)
trivy fs --scanners vuln,secret,misconfig .

# Scan Python requirements only
trivy fs --scanners vuln backend/requirements.txt

# JSON output for triage
trivy fs --format json --output .tmp/trivy-report.json .
```

---

## 6. OWASP ZAP (dynamic API scan — BASELINE ONLY)

> **CRITICAL:** Only `baseline.py` / `--spider` passive mode allowed.  
> **NEVER** run ZAP active scan (`zap-full-scan.py`) against the Nova backend while IB Gateway  
> is connected — active fuzzing can trigger unintended IBKR API calls.

Requires Docker Desktop running.

```powershell
# Pull image once
docker pull ghcr.io/zaproxy/zaproxy:stable

# Baseline passive scan against local dev server (API must be running on 8000)
docker run --rm --network host `
  ghcr.io/zaproxy/zaproxy:stable zap-baseline.py `
  -t http://host.docker.internal:8000 `
  -r zap-baseline-report.html

# Save report to local .tmp/
docker run --rm --network host `
  -v "${PWD}/.tmp:/zap/wrk" `
  ghcr.io/zaproxy/zaproxy:stable zap-baseline.py `
  -t http://host.docker.internal:8000 `
  -r /zap/wrk/zap-report.html
```

**Before running ZAP:**

1. Start Nova dev server (`Run Nova.bat`)
2. Confirm IB Gateway is **disconnected** or use `discovery=alpaca` mode
3. Run ZAP baseline only — no `-a` (active) flag
4. Review `zap-baseline-report.html` in `.tmp/`

---

## 7. cvss (CVSS v4 scoring — Python library)

Installed via `backend/requirements-dev.txt`.

```python
from cvss import CVSS4

# Example: parse a CVSS v4 vector from a pip-audit finding
c = CVSS4("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N")
print(c.scores())   # base score
print(c.severities())
```

`tools/security_audit.py` uses this to classify pip-audit JSON output by severity.

---

## Cursor agent roles

| Agent | Trigger | Scope |
|-------|---------|-------|
| `security-review` | "Review security of these changes" | Diff only (staged / branch changes) — fast |
| `security-sentinel` | "Run security sentinel" / full posture | Full repo: deps, secrets, patterns, CVSS classification |
| `llm-trading-agent-security` skill | Hardening exec paths / alert→IBKR paths | Methodology reference — research only |

### Running the CI audit locally

```powershell
# From repo root
python tools/security_audit.py --json

# Verbose human output
python tools/security_audit.py

# Fail on CRITICAL findings (for local gate before PR)
python tools/security_audit.py --fail-on-findings
```

---

## Baseline acceptance workflow

1. Run `python tools/security_audit.py --json > .tmp/security-baseline.json`
2. Review findings in `knowledge/obsidian/03-Nova-Decisions/Security-Status.md`
3. Triage: accept / fix / track each finding
4. After baseline accepted, enable `--fail-on-findings` in CI for new CRITICAL/HIGH findings
5. Update `Security-Status.md` with baseline SHA and open findings count

---

## Files to keep out of git

```text
.tmp/gitleaks-report.json
.tmp/trivy-report.json
.tmp/zap-report.html
.tmp/security-baseline.json
```

Add to `.gitignore` if running locally. Never commit scanner output with API keys, tokens, or
credentials visible in findings.
