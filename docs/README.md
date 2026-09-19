# docs/

## L2 Brain

[l2-brain-sensors.md](l2-brain-sensors.md) -- Sensor list v1, **18 sensors**
(implemented). Read-only GET smoke-test surface plus Settings &gt; Sensors
board. Sensor 13 news/catalyst is wired to the existing **Advice feature**.
Sensors 14-15 are wired to existing risk/halt sources. Sensor 16 is a new
small local decision log (stub). Sensor 17 regime is computed/stub. Sensor
18 macro calendar is a stub (not the Advice feature). No new API keys.
See also [advise-rail.md](advise-rail.md) and [sim-mode.md](sim-mode.md).

[nova-brain.md](nova-brain.md) -- Windows `python -m nova_brain` worker.
OpenRouter is the llm-decide model (shared `OPENROUTER_API_KEY` with Advise).
Reads `/api/health`, bot session, focus, and `/sensors/snapshot`. L1 proposes;
L2 + Activate may fire allowlisted actions.

## Warrior Trading materials

Canonical local library (gitignored under `downloads/`):

| Path | Contents |
|------|----------|
| `downloads/warrior-trading-slides/` | LMS slide PDFs + layout packs by course |
| `downloads/warrior-trading-resources/` | Free ebook, Excel trade sheets, eSignal zips |
| `downloads/warrior-trading-caption-notes/` | Transcript / caption notes |
| `downloads/warrior-trading-videos/` | Local course videos |

**Do not** re-download into `docs/warrior-trading/` — that duplicate tree was removed after merging unique files into `downloads/` (2026-07-14).

Authenticated member website / Day Trade Dash navigation (live map for agents):
[warrior-authenticated-access.md](warrior-authenticated-access.md) · Obsidian `01-Courses/Warrior-Trading/Authenticated-Site-Map.md` · launcher `scripts/open_warrior_site.ps1`.

### Added in the 2026-07-14 merge (were missing before)

- Free ebook → `downloads/warrior-trading-resources/free/`
- Excel + eSignal → `downloads/warrior-trading-resources/{excel,esignal}/`
- SS `ss-07` parts + `ss-16`…`ss-20` → Strategies & Scaling
- Trader Rehab PDF, Jess/Danny/Max grad PDFs, Platform Demos layouts
