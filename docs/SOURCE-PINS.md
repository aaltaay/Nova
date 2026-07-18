# Documentation tool source pins

Verified upstream tools used by **Docs** (`.cursor/agents/docs.md`).  
Do not invent house style guides — use these packages as configured.

Last verified: **2026-07-16**

| Tool | Version | Upstream | Role |
|------|---------|----------|------|
| Diátaxis | methodology | https://diataxis.fr/ · https://github.com/evildmp/diataxis-documentation-framework | Information architecture (tutorial / how-to / reference / explanation) |
| markdownlint-cli2 | **0.23.0** | https://github.com/DavidAnson/markdownlint-cli2 | Markdown / MDC structure |
| Vale | **3.15.1** | https://github.com/errata-ai/vale | Prose lint |
| Vale packages | Google, write-good | https://github.com/errata-ai/packages · Vale Package Explorer | Google Developer Documentation Style Guide + write-good |
| Lychee | **0.24.2** | https://github.com/lycheeverse/lychee | Link checker |

## Run (repo root)

```text
npx --yes markdownlint-cli2@0.23.0 "**/*.{md,mdc}" "#node_modules" "#frontend/node_modules" "#.git" "#graphify-out"
vale sync
vale .
lychee --root-dir . "./**/*.md"
py -3 tools/nova_docs_inventory.py --json
```

## Windows install notes

- **markdownlint-cli2:** via `npx` (no global install required).
- **Vale:** install from GitHub Releases (`v3.15.1`) or Scoop/Chocolatey; then `vale sync` from repo root to populate `.vale/styles/` (gitignored).
- **Lychee:** install from GitHub Releases (`lychee-v0.24.2`) or Scoop/Chocolatey.

If Vale or Lychee is missing, Docs reports that gate as **BLOCKED** and continues with inventory + markdownlint + evidence-based review.
