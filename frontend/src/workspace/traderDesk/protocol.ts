/**
 * Trader desk codec -- drag payload + BroadcastChannel messages (ADR 011).
 * Pure. No React, no window.
 */

export const TRADER_DESK_PROTOCOL_V = 1 as const;

export const TRADER_DESK_CHANNEL = 'nova.trader.desk';
export const TRADER_TAB_DRAG_MIME = 'application/x-nova-trader-tab';
export const TRADER_TAB_DRAG_TEXT_PREFIX = 'nova-trader-tab:';

export type TraderDeskRole = 'host' | 'float';

export type TraderTabDragPayload = {
  v: typeof TRADER_DESK_PROTOCOL_V;
  symbol: string;
  sourceWindowId: string;
};

export type TraderDeskMessageType =
  | 'offer'
  | 'offer-end'
  | 'dock-request'
  | 'tab-docked'
  | 'dock-reject';

export type TraderDeskMessage = {
  v: typeof TRADER_DESK_PROTOCOL_V;
  type: TraderDeskMessageType;
  symbol?: string;
  sourceWindowId: string;
  targetWindowId?: string;
  requestId?: string;
};

function normSymbol(symbol: string): string {
  return symbol.trim().toUpperCase();
}

export function encodeTraderTabDrag(input: {
  symbol: string;
  sourceWindowId: string;
}): string {
  const payload: TraderTabDragPayload = {
    v: TRADER_DESK_PROTOCOL_V,
    symbol: normSymbol(input.symbol),
    sourceWindowId: input.sourceWindowId,
  };
  return JSON.stringify(payload);
}

export function parseTraderTabDrag(raw: string | null | undefined): TraderTabDragPayload | null {
  if (!raw) return null;
  const text = raw.startsWith(TRADER_TAB_DRAG_TEXT_PREFIX)
    ? raw.slice(TRADER_TAB_DRAG_TEXT_PREFIX.length)
    : raw;
  try {
    const data = JSON.parse(text) as Partial<TraderTabDragPayload>;
    if (data.v !== TRADER_DESK_PROTOCOL_V) return null;
    const symbol = typeof data.symbol === 'string' ? normSymbol(data.symbol) : '';
    const sourceWindowId = typeof data.sourceWindowId === 'string' ? data.sourceWindowId : '';
    if (!symbol || !sourceWindowId) return null;
    return { v: TRADER_DESK_PROTOCOL_V, symbol, sourceWindowId };
  } catch {
    return null;
  }
}

export function traderDeskMessage(
  type: TraderDeskMessageType,
  fields: Omit<TraderDeskMessage, 'v' | 'type'>,
): TraderDeskMessage {
  const symbol = fields.symbol ? normSymbol(fields.symbol) : undefined;
  return {
    v: TRADER_DESK_PROTOCOL_V,
    type,
    sourceWindowId: fields.sourceWindowId,
    ...(symbol ? { symbol } : {}),
    ...(fields.targetWindowId ? { targetWindowId: fields.targetWindowId } : {}),
    ...(fields.requestId ? { requestId: fields.requestId } : {}),
  };
}

export function parseTraderDeskMessage(raw: unknown): TraderDeskMessage | null {
  if (!raw || typeof raw !== 'object') return null;
  const data = raw as Partial<TraderDeskMessage>;
  if (data.v !== TRADER_DESK_PROTOCOL_V) return null;
  if (
    data.type !== 'offer'
    && data.type !== 'offer-end'
    && data.type !== 'dock-request'
    && data.type !== 'tab-docked'
    && data.type !== 'dock-reject'
  ) {
    return null;
  }
  if (typeof data.sourceWindowId !== 'string' || !data.sourceWindowId) return null;
  const symbol = typeof data.symbol === 'string' ? normSymbol(data.symbol) : undefined;
  if (
    (data.type === 'offer' || data.type === 'dock-request' || data.type === 'tab-docked' || data.type === 'dock-reject')
    && !symbol
  ) {
    return null;
  }
  return {
    v: TRADER_DESK_PROTOCOL_V,
    type: data.type,
    sourceWindowId: data.sourceWindowId,
    ...(symbol ? { symbol } : {}),
    ...(typeof data.targetWindowId === 'string' ? { targetWindowId: data.targetWindowId } : {}),
    ...(typeof data.requestId === 'string' ? { requestId: data.requestId } : {}),
  };
}

export function writeTraderTabDrag(
  dt: Pick<DataTransfer, 'setData' | 'effectAllowed'>,
  payload: { symbol: string; sourceWindowId: string },
): void {
  const json = encodeTraderTabDrag(payload);
  dt.effectAllowed = 'move';
  try {
    dt.setData(TRADER_TAB_DRAG_MIME, json);
  } catch {
    /* some browsers reject custom MIME */
  }
  dt.setData('text/plain', `${TRADER_TAB_DRAG_TEXT_PREFIX}${json}`);
}

export function readTraderTabDrag(
  dt: Pick<DataTransfer, 'getData'>,
): TraderTabDragPayload | null {
  let raw = '';
  try {
    raw = dt.getData(TRADER_TAB_DRAG_MIME);
  } catch {
    raw = '';
  }
  if (!raw) {
    try {
      raw = dt.getData('text/plain');
    } catch {
      raw = '';
    }
  }
  return parseTraderTabDrag(raw);
}

export function dataTransferHasTraderTab(types: ArrayLike<string> | null | undefined): boolean {
  if (!types) return false;
  const list = Array.from(types);
  return list.includes(TRADER_TAB_DRAG_MIME) || list.includes('text/plain');
}
