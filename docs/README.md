# docs/

## L2 Brain

[l2-brain-sensors.md](l2-brain-sensors.md) -- Sensor list v1, **18 sensors**
(implemented). Read-only GET smoke-test surface plus Settings &gt; Sensors
board. Sensor 13 news/catalyst is wired to the existing **Advice feature**.
Sensors 14-15 are wired to existing risk/halt sources. Sensor 16 is a new
small local decision log (stub). Sensor 17 regime is computed/stub. Sensor
18 macro calendar is a stub (not the Advice feature). No new API keys.
See also [advise-rail.md](advise-rail.md) and [sim-mode.md](sim-mode.md).

The `nova-brain` worker and its packs were retired by ADR 027; the bot plays
the operator's setups, and Strategy waits on the first-pullback read-out
([bot-localhost-api.md](bot-localhost-api.md)).
