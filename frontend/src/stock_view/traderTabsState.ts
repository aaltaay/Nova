/**
 * Pure Trader-tab state machine -- unit-tested, no React.
 * Strip is unbounded. Live L2 slots are capped at maxLive (IBKR depth plan).
 */

export type TraderTabsState = {
  tabs: string[];
  active: string | null;
  /** Live L2 symbols, oldest-focus first (index 0 is evicted first). */
  live: string[];
};

export type TraderTabsResult = {
  state: TraderTabsState;
  blocked: boolean;
};

export const EMPTY_TRADER_TABS: TraderTabsState = { tabs: [], active: null, live: [] };

/** Empty-string draft tab used by the "+" affordance before the user commits a symbol. */
export const TRADER_DRAFT_SYMBOL = '';

function norm(symbol: string): string {
  return symbol.trim().toUpperCase();
}

function keyOf(symbol: string): string {
  return symbol === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : norm(symbol);
}

function liveOf(state: TraderTabsState): string[] {
  const tabs = state.tabs;
  const raw = Array.isArray(state.live) ? state.live : [];
  return raw.filter(
    (s, i, arr) => s && s !== TRADER_DRAFT_SYMBOL && tabs.includes(s) && arr.indexOf(s) === i,
  );
}

export function isTabLive(state: TraderTabsState, symbol: string): boolean {
  const sym = keyOf(symbol);
  if (!sym) return false;
  return liveOf(state).includes(sym);
}

/** Move symbol to most-recent live; evict oldest when over maxLive. */
export function promoteLive(
  state: TraderTabsState,
  symbol: string,
  maxLive: number,
): TraderTabsState {
  const sym = keyOf(symbol);
  const liveNow = liveOf(state);
  if (!sym || !state.tabs.includes(sym)) {
    return { tabs: state.tabs, active: state.active, live: liveNow };
  }
  const others = liveNow.filter((s) => s !== sym);
  let live = [...others, sym];
  if (maxLive > 0 && live.length > maxLive) {
    live = live.slice(live.length - maxLive);
  }
  return { tabs: state.tabs, active: state.active, live };
}

export function activateTab(
  state: TraderTabsState,
  symbol: string,
  maxLive: number,
): TraderTabsState {
  const raw = keyOf(symbol);
  const liveNow = liveOf(state);
  if (raw === TRADER_DRAFT_SYMBOL) {
    if (!state.tabs.includes(TRADER_DRAFT_SYMBOL)) {
      return { tabs: state.tabs, active: state.active, live: liveNow };
    }
    return { tabs: state.tabs, active: TRADER_DRAFT_SYMBOL, live: liveNow };
  }
  if (!state.tabs.includes(raw)) {
    return { tabs: state.tabs, active: state.active, live: liveNow };
  }
  return promoteLive({ tabs: state.tabs, active: raw, live: liveNow }, raw, maxLive);
}

export function addTab(
  state: TraderTabsState,
  symbol: string,
  maxLive: number,
): TraderTabsResult {
  const sym = norm(symbol);
  const liveNow = liveOf(state);
  if (!sym) return { state: { tabs: state.tabs, active: state.active, live: liveNow }, blocked: false };
  if (state.tabs.includes(sym)) {
    return { state: activateTab(state, sym, maxLive), blocked: false };
  }
  const tabs = [...state.tabs, sym];
  return {
    state: activateTab({ tabs, active: sym, live: liveNow }, sym, maxLive),
    blocked: false,
  };
}

/** Open a draft (empty) tab for inline rename. Strip is unbounded. */
export function addDraftTab(state: TraderTabsState): TraderTabsResult {
  const liveNow = liveOf(state);
  if (state.tabs.includes(TRADER_DRAFT_SYMBOL)) {
    return {
      state: { tabs: state.tabs, active: TRADER_DRAFT_SYMBOL, live: liveNow },
      blocked: false,
    };
  }
  return {
    state: {
      tabs: [...state.tabs, TRADER_DRAFT_SYMBOL],
      active: TRADER_DRAFT_SYMBOL,
      live: liveNow,
    },
    blocked: false,
  };
}

export function closeTab(state: TraderTabsState, symbol: string): TraderTabsState {
  const raw = keyOf(symbol);
  const idx = state.tabs.indexOf(raw);
  if (idx < 0) return { tabs: state.tabs, active: state.active, live: liveOf(state) };
  const tabs = state.tabs.filter((t) => t !== raw);
  const live = liveOf(state).filter((s) => s !== raw);
  if (tabs.length === 0) return EMPTY_TRADER_TABS;
  let active = state.active;
  if (active === raw) {
    active = tabs[Math.min(idx, tabs.length - 1)] ?? null;
  }
  return { tabs, active, live };
}

/**
 * Rename (or commit a draft). If `to` already exists, focuses that tab and
 * drops `from` when it was a draft or a distinct duplicate rename.
 */
export function renameTab(
  state: TraderTabsState,
  from: string,
  to: string,
  maxLive: number,
): TraderTabsResult {
  const fromKey = keyOf(from);
  const toSym = norm(to);
  const liveNow = liveOf(state);
  if (!state.tabs.includes(fromKey)) {
    return { state: { tabs: state.tabs, active: state.active, live: liveNow }, blocked: false };
  }
  if (!toSym) {
    if (fromKey === TRADER_DRAFT_SYMBOL) {
      return { state: closeTab(state, TRADER_DRAFT_SYMBOL), blocked: false };
    }
    return { state: { tabs: state.tabs, active: state.active, live: liveNow }, blocked: false };
  }
  if (fromKey === toSym) {
    return { state: activateTab(state, toSym, maxLive), blocked: false };
  }
  if (state.tabs.includes(toSym)) {
    const withoutFrom = closeTab(state, fromKey);
    return { state: activateTab(withoutFrom, toSym, maxLive), blocked: false };
  }
  const tabs = state.tabs.map((t) => (t === fromKey ? toSym : t));
  const live = liveNow.map((s) => (s === fromKey ? toSym : s));
  return {
    state: activateTab({ tabs, active: toSym, live }, toSym, maxLive),
    blocked: false,
  };
}

/** After extracting a gray tab, drop the oldest live slot so the float can take it. */
export function releaseOldestLive(state: TraderTabsState): TraderTabsState {
  const live = liveOf(state);
  if (live.length === 0) return { tabs: state.tabs, active: state.active, live };
  const nextLive = live.slice(1);
  let active = state.active;
  if (active && active !== TRADER_DRAFT_SYMBOL && !nextLive.includes(active) && nextLive.length) {
    active = nextLive[nextLive.length - 1] ?? active;
  }
  return { tabs: state.tabs, active, live: nextLive };
}

export function capLive(state: TraderTabsState, maxLive: number): TraderTabsState {
  const live = liveOf(state);
  if (maxLive <= 0 || live.length <= maxLive) {
    return { tabs: state.tabs, active: state.active, live };
  }
  return { tabs: state.tabs, active: state.active, live: live.slice(live.length - maxLive) };
}

export type PersistedTraderTabs = {
  tabs: string[];
  active: string | null;
  live?: string[];
};

export function serializeTraderTabs(state: TraderTabsState): string {
  const tabs = state.tabs.filter((t) => t !== TRADER_DRAFT_SYMBOL);
  const live = liveOf(state).filter((s) => tabs.includes(s));
  const active =
    state.active && state.active !== TRADER_DRAFT_SYMBOL && tabs.includes(state.active)
      ? state.active
      : tabs[0] ?? null;
  return JSON.stringify({ tabs, active, live } satisfies PersistedTraderTabs);
}

function defaultLive(tabs: string[], active: string | null, persisted?: string[]): string[] {
  if (Array.isArray(persisted) && persisted.length) {
    return persisted.filter((s, i, arr) => s && tabs.includes(s) && arr.indexOf(s) === i);
  }
  const seeded = tabs.filter(Boolean);
  if (active && seeded.includes(active)) {
    const without = seeded.filter((s) => s !== active);
    return [...without, active];
  }
  return seeded;
}

export function parseTraderTabs(raw: string | null): TraderTabsState {
  if (!raw) return EMPTY_TRADER_TABS;
  try {
    const data = JSON.parse(raw) as PersistedTraderTabs;
    if (!Array.isArray(data.tabs)) return EMPTY_TRADER_TABS;
    const tabs = data.tabs
      .map((t) => (typeof t === 'string' ? norm(t) : ''))
      .filter(Boolean)
      .filter((t, i, arr) => arr.indexOf(t) === i);
    const active =
      typeof data.active === 'string' && tabs.includes(norm(data.active))
        ? norm(data.active)
        : tabs[0] ?? null;
    const persistedLive = Array.isArray(data.live)
      ? data.live.map((s) => (typeof s === 'string' ? norm(s) : ''))
      : undefined;
    return { tabs, active, live: defaultLive(tabs, active, persistedLive) };
  } catch {
    return EMPTY_TRADER_TABS;
  }
}

/** Merge a URL/intent symbol into stored tabs (focus if present, else add). */
export function hydrateWithSymbol(
  stored: TraderTabsState,
  symbol: string | null,
  maxLive: number,
): TraderTabsResult {
  if (!symbol) return { state: capLive(stored, maxLive), blocked: false };
  return addTab(stored, symbol, maxLive);
}
