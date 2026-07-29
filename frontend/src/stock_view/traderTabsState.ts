/**
 * Pure Trader-tab state machine — unit-tested, no React.
 * Cap = TRADER_MAX_TABS (matches IBKR depth plan).
 */

export type TraderTabsState = {
  tabs: string[];
  active: string | null;
};

export type TraderTabsResult = {
  state: TraderTabsState;
  blocked: boolean;
};

export const EMPTY_TRADER_TABS: TraderTabsState = { tabs: [], active: null };

/** Empty-string draft tab used by the "+" affordance before the user commits a symbol. */
export const TRADER_DRAFT_SYMBOL = '';

function norm(symbol: string): string {
  return symbol.trim().toUpperCase();
}

export function activateTab(state: TraderTabsState, symbol: string): TraderTabsState {
  const sym = norm(symbol);
  if (!sym || !state.tabs.includes(sym)) return state;
  return { tabs: state.tabs, active: sym };
}

export function addTab(
  state: TraderTabsState,
  symbol: string,
  maxTabs: number,
): TraderTabsResult {
  const sym = norm(symbol);
  if (!sym) return { state, blocked: false };
  if (state.tabs.includes(sym)) {
    return { state: { tabs: state.tabs, active: sym }, blocked: false };
  }
  if (state.tabs.length >= maxTabs) {
    return { state, blocked: true };
  }
  return { state: { tabs: [...state.tabs, sym], active: sym }, blocked: false };
}

/** Open a draft (empty) tab for inline rename; blocked at cap. */
export function addDraftTab(state: TraderTabsState, maxTabs: number): TraderTabsResult {
  if (state.tabs.includes(TRADER_DRAFT_SYMBOL)) {
    return { state: { tabs: state.tabs, active: TRADER_DRAFT_SYMBOL }, blocked: false };
  }
  if (state.tabs.length >= maxTabs) {
    return { state, blocked: true };
  }
  return {
    state: { tabs: [...state.tabs, TRADER_DRAFT_SYMBOL], active: TRADER_DRAFT_SYMBOL },
    blocked: false,
  };
}

export function closeTab(state: TraderTabsState, symbol: string): TraderTabsState {
  const raw = symbol === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : norm(symbol);
  const idx = state.tabs.indexOf(raw);
  if (idx < 0) return state;
  const tabs = state.tabs.filter(t => t !== raw);
  if (tabs.length === 0) return EMPTY_TRADER_TABS;
  let active = state.active;
  if (active === raw) {
    active = tabs[Math.min(idx, tabs.length - 1)] ?? null;
  }
  return { tabs, active };
}

/**
 * Rename (or commit a draft). If `to` already exists, focuses that tab and
 * drops `from` when it was a draft or a distinct duplicate rename.
 */
export function renameTab(
  state: TraderTabsState,
  from: string,
  to: string,
  maxTabs: number,
): TraderTabsResult {
  const fromKey = from === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : norm(from);
  const toSym = norm(to);
  if (!state.tabs.includes(fromKey)) return { state, blocked: false };
  if (!toSym) {
    // Empty commit on draft → close draft; empty rename of real tab → no-op
    if (fromKey === TRADER_DRAFT_SYMBOL) {
      return { state: closeTab(state, TRADER_DRAFT_SYMBOL), blocked: false };
    }
    return { state, blocked: false };
  }
  if (fromKey === toSym) {
    return { state: { tabs: state.tabs, active: toSym }, blocked: false };
  }
  if (state.tabs.includes(toSym)) {
    // Focus existing; remove the source tab (draft or accidental dup rename)
    const withoutFrom = closeTab(state, fromKey);
    return { state: { tabs: withoutFrom.tabs, active: toSym }, blocked: false };
  }
  // Cap check only matters if somehow adding (shouldn't for rename of existing)
  if (fromKey === TRADER_DRAFT_SYMBOL && state.tabs.filter(t => t !== TRADER_DRAFT_SYMBOL).length >= maxTabs) {
    return { state, blocked: true };
  }
  const tabs = state.tabs.map(t => (t === fromKey ? toSym : t));
  return { state: { tabs, active: toSym }, blocked: false };
}

export type PersistedTraderTabs = {
  tabs: string[];
  active: string | null;
};

export function serializeTraderTabs(state: TraderTabsState): string {
  // Never persist an empty draft
  const tabs = state.tabs.filter(t => t !== TRADER_DRAFT_SYMBOL);
  const active =
    state.active && state.active !== TRADER_DRAFT_SYMBOL && tabs.includes(state.active)
      ? state.active
      : tabs[0] ?? null;
  return JSON.stringify({ tabs, active } satisfies PersistedTraderTabs);
}

export function parseTraderTabs(raw: string | null): TraderTabsState {
  if (!raw) return EMPTY_TRADER_TABS;
  try {
    const data = JSON.parse(raw) as PersistedTraderTabs;
    if (!Array.isArray(data.tabs)) return EMPTY_TRADER_TABS;
    const tabs = data.tabs
      .map(t => (typeof t === 'string' ? norm(t) : ''))
      .filter(Boolean)
      .filter((t, i, arr) => arr.indexOf(t) === i);
    const active =
      typeof data.active === 'string' && tabs.includes(norm(data.active))
        ? norm(data.active)
        : tabs[0] ?? null;
    return { tabs, active };
  } catch {
    return EMPTY_TRADER_TABS;
  }
}

/** Merge a URL/intent symbol into stored tabs (focus if present, else add). */
export function hydrateWithSymbol(
  stored: TraderTabsState,
  symbol: string | null,
  maxTabs: number,
): TraderTabsResult {
  if (!symbol) return { state: stored, blocked: false };
  return addTab(stored, symbol, maxTabs);
}
