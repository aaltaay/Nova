# Dependency rules (mechanical)

Maintainer and agents classify any new import or file placement as **allowed** or **forbidden** using this document alone.  
Phase 1 adds warning-first checks; new violations after the warning baseline must fail CI/maintainer `--fail-on-findings` once enabled.

## Backend layers

```
Delivery (routes/, WS handlers)
  → Application (scan_runners, ticker assembly, loops, use cases)
    → Domain (pure rules/models: hod_momo_filters, news rules, nova_os gates)
    → Ports (Protocol contracts)
Adapters (ibkr/, alpaca, archive/r2, sqlite/json) implement Ports
Composition (main.py, app_lifespan, explicit state modules) wires adapters → delivery
```

### Allowed

| From | May import |
|------|------------|
| Delivery | Application, Domain (read-only models), typed state providers |
| Application | Domain, Ports, typed state providers |
| Domain | stdlib + other Domain only (no FastAPI, no `ibkr` SDK, no `main`) |
| Adapters | Ports, Domain models, vendor SDKs, I/O |
| Composition | Delivery, Application, Adapters, state modules |

### Forbidden

| Violation | Why |
|-----------|-----|
| Domain or Application `import main` / `from main import …` for caches | State must live in explicit owners (Phase 7) |
| Domain importing FastAPI routes or concrete adapters | Breaks inward dependency |
| Routes mutating scanner caches directly | Delivery must call Application/state APIs |
| Silent IBKR→Alpaca (or reverse) price fallback in adapters | Single-market-data-feed rule |
| New production module reaching into another adapter's private helpers without a port | Coupling |

**Exception:** tests may `from main import app`. Tooling under `tools/` is outside the runtime graph.

### State ownership

| Concern | Owner (target) |
|---------|----------------|
| Scanner caches (gappers/gainers/losers/movers) | `backend/runtime_state/` or `scanner_state` module (Phase 7) |
| HOD Momo mutable engine state | Explicit HOD state owner (Phase 10) |
| IBKR depth subscriptions | Depth state module (Phase 9) |
| Broker order mutations | `execution.service.execute` → `ibkr/orders.py` only (ADR 007) |
| App wiring / lifespan | `main.py` + `app_lifespan.py` only |

## Frontend layers

```
App / pages (composition)
  → Workspace shell (registry, selected symbol, layout)
  → Feature slices (hod_momo/, hotkeys/, chart/, ibkr/, …)
    → Shared kernel (components primitives, generic hooks, tokens, utils)
```

### Allowed

| From | May import |
|------|------------|
| App / pages | Workspace public API, feature public barrels, shared |
| Workspace | Shared, feature public APIs |
| Feature | Shared, workspace public contracts, **own** internals |
| Shared | Shared only (no feature internals) |

### Forbidden

| Violation | Why |
|-----------|-----|
| New business feature files at `frontend/src/` root | Features live in feature folders |
| Feature A importing Feature B internals (deep paths) | Use public API / workspace / events |
| Types exported only from large components | Types live in `types/` or feature `types` |
| New domain constants only in god `constants.ts` after Phase 3 | Domain modules + barrel |
| New global CSS blocks without named owner/layer after Phase 2 | styles/ or feature CSS |

## CSS layers (native `@layer` order)

Declared order (specificity from general → specific):

1. `reset`
2. `tokens`
3. `base`
4. `layout`
5. `components`
6. `features`
7. `utilities`
8. `overrides`

`index.css` is import-only (≤50 lines) after Phase 2. Domain stylesheets prefer &lt;700 lines, hard &lt;1000.

## Compatibility / facade policy

- Old import paths may re-export new modules (Strangler Facade) until callers migrate.
- Every facade documents: **owner phase**, **removal criterion** (e.g. “no remaining deep imports in grep”).
- Facades must not add business logic; only re-exports or thin delegation.

## Enforcement hooks

| Check | Phase |
|-------|-------|
| CSS line limits + `index.css` hard cap | 1–2 |
| Accepted-baseline **growth** (hod_momo, executor) | 1 |
| Production `import main` for state | 1 warn → 7 eliminate |
| Cross-feature deep imports | blocking via public feature barrels (`workspace/`, `modules/`, `ibkr/`, `chart/`) |
| Layer import direction (representative) | 1 warn |
