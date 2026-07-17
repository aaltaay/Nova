# Security Tool Source Pins

Pinned versions and roles for every OSS tool used in the Nova security audit stack.
Update this file whenever a tool is upgraded; keep it in sync with `tools/security_audit.py`.

---

## Active Tools (integrated in `tools/security_audit.py`)

### Semgrep CE

- **GitHub:** https://github.com/semgrep/semgrep
- **Role:** Static application security testing (SAST). Detects hardcoded secrets, injection sinks, dangerous patterns in Python and TypeScript. CE edition; no telemetry flags needed for offline runs.
- **Install:** `pip install semgrep` or `brew install semgrep`
- **Invoked as:** `semgrep --config auto --json <path>`
- **Pin target:** ≥ 1.90.0

### Gitleaks

- **GitHub:** https://github.com/gitleaks/gitleaks
- **Role:** Git history secret scanning. Scans commits and working tree for leaked credentials (API keys, tokens, private keys). Runs before every deploy.
- **Install:** `winget install gitleaks` / binary release from GitHub releases
- **Invoked as:** `gitleaks detect --source <repo> --report-format json --report-path -`
- **Pin target:** ≥ 8.25.0

### OSV-Scanner

- **GitHub:** https://github.com/google/osv-scanner
- **Role:** Dependency vulnerability scanning against OSV database. Scans `requirements.txt` (Python) and `package-lock.json` (Node). Covers both CVE and GHSA advisories.
- **Install:** Binary release from https://github.com/google/osv-scanner/releases
- **Invoked as:** `osv-scanner --format json --lockfile <lockfile>`
- **Pin target:** ≥ 1.9.0

### Trivy

- **GitHub:** https://github.com/aquasecurity/trivy
- **Role:** Container, filesystem, and SBOM vulnerability scanner. Scans both Python and Node dependency manifests; also scans Dockerfiles for misconfigurations.
- **Install:** `winget install AquaSecurity.Trivy` / binary release
- **Invoked as:** `trivy fs --format json --quiet <path>`
- **Pin target:** ≥ 0.58.0

### pip-audit

- **GitHub:** https://github.com/pypa/pip-audit
- **Role:** Python dependency vulnerability audit using PyPI Advisory Database and OSV. Complements OSV-Scanner with pip-specific resolution.
- **Install:** `pip install pip-audit`
- **Invoked as:** `pip-audit --format json --requirement <requirements.txt>`
- **Pin target:** ≥ 2.9.0
- **Note:** Available via `pip_audit` module as well as CLI.

### npm audit

- **Role:** Node.js dependency vulnerability audit (built-in to npm).
- **Install:** Bundled with Node.js / npm ≥ 6.
- **Invoked as:** `npm audit --json`
- **Note:** Must be run from `frontend/` directory.

---

## Reference Frameworks (methodology only — not invoked as binaries)

### Red Hat CVSS Calculator

- **GitHub:** https://github.com/RedHatProductSecurity/cvss
- **Role:** CVSS 3.1 vector validation and score computation.
- **Use:** Score verification for findings that specify `cvss_vector`. Not invoked at scan time.

### OWASP ASVS 5.0

- **URL:** https://github.com/OWASP/ASVS/tree/v5.0.0
- **Role:** Application Security Verification Standard. Used to assign `asvs` field references to findings. Provides structured verification requirements for authentication, API security, data protection, etc.
- **Use:** Documentation / finding classification only. Not executed.

### OWASP Secure Agent Playbook

- **URL:** https://github.com/OWASP/www-project-secure-agent-playbook
- **Role:** Methodology guide for autonomous agent security. Informs built-in checks for Nova OS executor routes (unauthenticated actions, kill-switch bypass, injection via trade signals).
- **Use:** Methodology only. Not executed.

---

## Deferred Tools (not yet integrated)

| Tool | GitHub | Reason Deferred |
|------|--------|----------------|
| TruffleHog | https://github.com/trufflesecurity/trufflehog | Extended coverage overlaps Gitleaks; adds PR scanning; deferred until CI integration |
| Nuclei | https://github.com/projectdiscovery/nuclei | Active HTTP probing — requires `require_ibkr_disabled=true` and strict allowlist enforcement |
| Schemathesis | https://github.com/schemathesis/schemathesis | Fuzzing mutating/credential endpoints is blocked; profile defined in `safe_api_profile.json`; deferred until safe_api_profile enforcement is wired |
| ZAP (active mode) | https://github.com/zaproxy/zaproxy | Active scan against trading routes is forbidden; passive-only ZAP deferred pending loopback-only setup |

---

## Separation from Cursor Security-Review Agent

The **security-review Cursor subagent** (`skills/review-security/SKILL.md`) operates on
**git diffs only** — it reviews changed code in a PR and does not scan the full repository or
write to the findings registry. It is complementary to (not a replacement for) this tool stack.

**Do not** route security-review subagent output into `findings-registry.json` without manual
triage. The two systems must not collide: the registry is for deterministic scanner output only.
