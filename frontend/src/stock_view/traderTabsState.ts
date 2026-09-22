/**
 * Pure Trader-tab state machine -- unit-tested, no React.
 * Strip is unbounded. Live L2 slots are capped at maxLive (IBKR depth plan).
 *
 * Preview tabs (ADR 011, amended 2026-09-22): a ticker opened by a click lands
 * in the strip's *preview* tab -- the one unpinned symbol -- replacing whatever
 * was there, so browsing the scanner never piles up tabs. A tab the operator
 * pins (pin icon, or right-click > Pin) stays until closed. A symbol typed into
 * the strip, a rename and a docked tab are deliberate, so they arrive pinned.
 * Tabs stored before this rule existed are read back pinned: nothing an operator
 * left open is replaced by surprise.
 */

export type TraderTabsState = {
  tabs: string[];
  active: string | null;
  /** Live L2 symbols, oldest-focus first (index 0 is evicted first). */
  live: string[];
  /** Symbols the operator pinned; every other symbol tab is the preview. */
  pinned: string[];
};

export type TraderTabsResult = {
  state: TraderTabsState;
  blocked: boolean;
};

export const EMPTY_TRADER_TABS: TraderTabsState = { tabs: [], active: null, live: [], pinned: [] };

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

/**
 * Pinned symbols, restricted to the strip. A state with no `pinned` field is
 * from before preview tabs existed: every symbol on it counts as pinned.
 */
function pinnedOf(state: TraderTabsState): string[] {
  const tabs = state.tabs;
  const raw = (state as Partial<TraderTabsState>).pinned;
  if (!Array.isArray(raw)) return tabs.filter((t) => t !== TRADER_DRAFT_SYMBOL);
  return raw.filter(
    (s, i, arr) => s && s !== TRADER_DRAFT_SYMBOL && tabs.includes(s) && arr.indexOf(s) === i,
  );
}

function make(tabs: string[], active: string | null, live: string[], pinned: string[]): TraderTabsState {
  return { tabs, active, live, pinned };
}

/** Same tabs, normalised live / pinned lists (what every no-op returns). */
function same(state: TraderTabsState): TraderTabsState {
  return make(state.tabs, state.active, liveOf(state), pinnedOf(state));
}

export function isTabLive(state: TraderTabsState, symbol: string): boolean {
  const sym = keyOf(symbol);
  if (!sym) return false;
  return liveOf(state).includes(sym);
}

export function isTabPinned(state: TraderTabsState, symbol: string): boolean {
  const sym = keyOf(symbol);
  if (!sym) return false;
  return pinnedOf(state).includes(sym);
}

/**
 * The tab a new ticker replaces: the active tab when it is an unpinned symbol,
 * else the most recently added unpinned symbol, else none.
 */
export function previewTabOf(state: TraderTabsState): string | null {
  const pinned = pinnedOf(state);
  const unpinned = state.tabs.filter((t) => t !== TRADER_DRAFT_SYMBOL && !pinned.includes(t));
  if (unpinned.length === 0) return null;
  if (state.active && unpinned.includes(state.active)) return state.active;
  return unpinned[unpinned.length - 1] ?? null;
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
    return same(state);
  }
  const others = liveNow.filter((s) => s !== sym);
  let live = [...others, sym];
  if (maxLive > 0 && live.length > maxLive) {
    live = live.slice(live.length - maxLive);
  }
  return make(state.tabs, state.active, live, pinnedOf(state));
}

export function activateTab(
  state: TraderTabsState,
  symbol: string,
  maxLive: number,
): TraderTabsState {
  const raw = keyOf(symbol);
  const liveNow = liveOf(state);
  const pinned = pinnedOf(state);
  if (raw === TRADER_DRAFT_SYMBOL) {
    if (!state.tabs.includes(TRADER_DRAFT_SYMBOL)) {
      return make(state.tabs, state.active, liveNow, pinned);
    }
    return make(state.tabs, TRADER_DRAFT_SYMBOL, liveNow, pinned);
  }
  if (!state.tabs.includes(raw)) {
    return make(state.tabs, state.active, liveNow, pinned);
  }
  return promoteLive(make(state.tabs, raw, liveNow, pinned), raw, maxLive);
}

export type AddTabOptions = {
  /** False for a deliberate arrival (a docked tab): append beside the preview instead of replacing it. */
  replacePreview?: boolean;
};

/**
 * Open a symbol: focus it when present; otherwise it takes the preview tab's
 * place (same position, same live slot) or, with nothing to replace, appends.
 */
export function addTab(
  state: TraderTabsState,
  symbol: string,
  maxLive: number,
  opts: AddTabOptions = {},
): TraderTabsResult {
  const sym = norm(symbol);
  const liveNow = liveOf(state);
  const pinned = pinnedOf(state);
  if (!sym) return { state: make(state.tabs, state.active, liveNow, pinned), blocked: false };
  if (state.tabs.includes(sym)) {
    return { state: activateTab(state, sym, maxLive), blocked: false };
  }
  const preview = opts.replacePreview === false ? null : previewTabOf(state);
  if (preview) {
    const tabs = state.tabs.map((t) => (t === preview ? sym : t));
    const live = liveNow.map((s) => (s === preview ? sym : s));
    return {
      state: activateTab(make(tabs, sym, live, pinned), sym, maxLive),
      blocked: false,
    };
  }
  const tabs = [...state.tabs, sym];
  return {
    state: activateTab(make(tabs, sym, liveNow, pinned), sym, maxLive),
    blocked: false,
  };
}

export function pinTab(state: TraderTabsState, symbol: string): TraderTabsState {
  const sym = keyOf(symbol);
  const pinned = pinnedOf(state);
  if (!sym || !state.tabs.includes(sym) || pinned.includes(sym)) return same(state);
  return make(state.tabs, state.active, liveOf(state), [...pinned, sym]);
}

export function unpinTab(state: TraderTabsState, symbol: string): TraderTabsState {
  const sym = keyOf(symbol);
  const pinned = pinnedOf(state);
  if (!sym || !pinned.includes(sym)) return same(state);
  return make(state.tabs, state.active, liveOf(state), pinned.filter((s) => s !== sym));
}

/** Open a draft (empty) tab for inline rename. Strip is unbounded. */
export function addDraftTab(state: TraderTabsState): TraderTabsResult {
  const liveNow = liveOf(state);
  const pinned = pinnedOf(state);
  if (state.tabs.includes(TRADER_DRAFT_SYMBOL)) {
    return {
      state: make(state.tabs, TRADER_DRAFT_SYMBOL, liveNow, pinned),
      blocked: false,
    };
  }
  return {
    state: make([...state.tabs, TRADER_DRAFT_SYMBOL], TRADER_DRAFT_SYMBOL, liveNow, pinned),
    blocked: false,
  };
}

export function closeTab(state: TraderTabsState, symbol: string): TraderTabsState {
  const raw = keyOf(symbol);
  const idx = state.tabs.indexOf(raw);
  if (idx < 0) return same(state);
  const tabs = state.tabs.filter((t) => t !== raw);
  const live = liveOf(state).filter((s) => s !== raw);
  const pinned = pinnedOf(state).filter((s) => s !== raw);
  if (tabs.length === 0) return EMPTY_TRADER_TABS;
  let active = state.active;
  if (active === raw) {
    active = tabs[Math.min(idx, tabs.length - 1)] ?? null;
  }
  return make(tabs, active, live, pinned);
}

/**
 * Rename (or commit a draft). If `to` already exists, focuses that tab and
 * drops `from` when it was a draft or a distinct duplicate rename. A typed
 * symbol is deliberate: the result is pinned.
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
  const pinned = pinnedOf(state);
  if (!state.tabs.includes(fromKey)) {
    return { state: make(state.tabs, state.active, liveNow, pinned), blocked: false };
  }
  if (!toSym) {
    if (fromKey === TRADER_DRAFT_SYMBOL) {
      return { state: closeTab(state, TRADER_DRAFT_SYMBOL), blocked: false };
    }
    return { state: make(state.tabs, state.active, liveNow, pinned), blocked: false };
  }
  if (fromKey === toSym) {
    return { state: pinTab(activateTab(state, toSym, maxLive), toSym), blocked: false };
  }
  if (state.tabs.includes(toSym)) {
    const withoutFrom = closeTab(state, fromKey);
    return { state: pinTab(activateTab(withoutFrom, toSym, maxLive), toSym), blocked: false };
  }
  const tabs = state.tabs.map((t) => (t === fromKey ? toSym : t));
  const live = liveNow.map((s) => (s === fromKey ? toSym : s));
  const nextPinned = [...pinned.filter((s) => s !== fromKey), toSym];
  return {
    state: activateTab(make(tabs, toSym, live, nextPinned), toSym, maxLive),
    blocked: false,
  };
}

/** After extracting a gray tab, drop the oldest live slot so the float can take it. */
export function releaseOldestLive(state: TraderTabsState): TraderTabsState {
  const live = liveOf(state);
  const pinned = pinnedOf(state);
  if (live.length === 0) return make(state.tabs, state.active, live, pinned);
  const nextLive = live.slice(1);
  let active = state.active;
  if (active && active !== TRADER_DRAFT_SYMBOL && !nextLive.includes(active) && nextLive.length) {
    active = nextLive[nextLive.length - 1] ?? active;
  }
  return make(state.tabs, active, nextLive, pinned);
}

export function capLive(state: TraderTabsState, maxLive: number): TraderTabsState {
  const live = liveOf(state);
  const pinned = pinnedOf(state);
  if (maxLive <= 0 || live.length <= maxLive) {
    return make(state.tabs, state.active, live, pinned);
  }
  return make(state.tabs, state.active, live.slice(live.length - maxLive), pinned);
}

export type PersistedTraderTabs = {
  tabs: string[];
  active: string | null;
  live?: string[];
  /** Absent in stores written before preview tabs: read back as "all pinned". */
  pinned?: string[];
};

export function serializeTraderTabs(state: TraderTabsState): string {
  const tabs = state.tabs.filter((t) => t !== TRADER_DRAFT_SYMBOL);
  const live = liveOf(state).filter((s) => tabs.includes(s));
  const pinned = pinnedOf(state).filter((s) => tabs.includes(s));
  const active =
    state.active && state.active !== TRADER_DRAFT_SYMBOL && tabs.includes(state.active)
      ? state.active
      : tabs[0] ?? null;
  return JSON.stringify({ tabs, active, live, pinned } satisfies PersistedTraderTabs);
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
    const pinned = Array.isArray(data.pinned)
      ? data.pinned
          .map((s) => (typeof s === 'string' ? norm(s) : ''))
          .filter((s, i, arr) => s && tabs.includes(s) && arr.indexOf(s) === i)
      : [...tabs];
    return make(tabs, active, defaultLive(tabs, active, persistedLive), pinned);
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
