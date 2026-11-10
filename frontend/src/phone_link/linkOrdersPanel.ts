/**
 * The Paper orders block of the phone link test (ADR 070, amendment 2026-11-10): the phone PIN,
 * Paper's padlock, and plain buttons for a buy, a sell, a flatten and a cancel, each answered with
 * the time from the tap to Nova's answer and Nova's own words. A measuring tool, not the order pad:
 * the pad the operator trades from is drawn and approved first.
 */
import { PhoneDoor, type Answer, type OrderContext, type PhoneStatus } from './linkOrders';

const LOG_KEEP = 8;
const STATUS_EVERY_MS = 5_000;

export const ORDERS_STYLE = `
  #orders { margin-top: 20px; padding-top: 12px; border-top: 1px solid #2a2f3a; }
  #orders .row { display: flex; gap: 8px; margin-bottom: 8px; }
  #orders .row > * { flex: 1; min-width: 0; }
  #orders button { padding: 12px 8px; }
  #orders button:disabled { opacity: 0.4; }
  #orders .buy { background: #12301f; border-color: #1f5236; }
  #orders .sell { background: #3a1518; border-color: #5e2327; }
  #orders #state { color: #c5cbd3; font-size: 13px; margin-bottom: 8px; }
  #orders #log { color: #c5cbd3; font-size: 13px; white-space: pre-line; font-variant-numeric: tabular-nums; }
  #orders #log .no { color: #ff8a8a; }
`;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text = '', id = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (id) node.id = id;
  return node;
}

function button(text: string, cls = ''): HTMLButtonElement {
  const b = el('button', text);
  b.type = 'button';
  if (cls) b.className = cls;
  return b;
}

/** Why the order buttons are off, in the operator's words; null when they may be pressed. */
export function blockedWhy(status: PhoneStatus | null, hasRun: boolean): string | null {
  if (!status) return 'Nova could not be reached.';
  if (!status.pin_set) return 'No phone PIN is set. On the PC: py -3 tools/set_phone_pin.py';
  if (!status.unlocked) return 'Locked. Enter your phone PIN.';
  if (!status.paper) return `The desk is on ${status.venue}: the phone trades Paper only. Switch the desk to Paper on the PC.`;
  if (!hasRun) return 'Press Start above first: an order needs the measured clock and a live Level 2.';
  return null;
}

/**
 * Why Buy alone is off, or null: a new entry needs the Level 2 this device received (the backend refuses one
 * without it, `PHONE_NO_VIEW`). Sell, Flatten and Cancel are ways out and never wait for it.
 */
export function buyBlockedWhy(ctx: OrderContext | null): string | null {
  if (!ctx) return null;
  if (ctx.offsetMs == null) return "Measuring the PC's clock: a buy waits for it.";
  if (!ctx.book || !ctx.instance) return `No Level 2 received for ${ctx.symbol} yet: a buy needs it. Sell, Flatten and Cancel still work.`;
  return null;
}

/** Build the block. `context` is the running test's view of the link, or null when no test runs. */
export function buildOrdersPanel(apiBase: string, context: () => OrderContext | null): HTMLElement {
  const door = new PhoneDoor(apiBase);
  let status: PhoneStatus | null = null;
  let busy = false;
  const lines: { text: string; ok: boolean }[] = [];

  const root = el('section', '', 'orders');
  root.append(el('h2', 'Paper orders'));
  const state = el('div', 'Reading...', 'state');

  const pinRow = el('div');
  pinRow.className = 'row';
  const pinInput = el('input');
  pinInput.type = 'password';
  pinInput.inputMode = 'numeric';
  pinInput.autocomplete = 'off';
  pinInput.maxLength = 6;
  pinInput.placeholder = 'Phone PIN';
  pinInput.style.textTransform = 'none';
  const unlockButton = button('Unlock');
  const padlockButton = button('Open padlock');
  pinRow.append(pinInput, unlockButton, padlockButton);

  const sizeRow = el('div');
  sizeRow.className = 'row';
  const qtyInput = el('input');
  qtyInput.inputMode = 'numeric';
  qtyInput.placeholder = 'Shares';
  qtyInput.value = '1';
  const priceInput = el('input');
  priceInput.inputMode = 'decimal';
  priceInput.placeholder = 'Limit (blank = market)';
  priceInput.style.textTransform = 'none';
  sizeRow.append(qtyInput, priceInput);

  const sendRow = el('div');
  sendRow.className = 'row';
  const buyButton = button('Buy', 'buy');
  const sellButton = button('Sell', 'sell');
  sendRow.append(buyButton, sellButton);

  const outRow = el('div');
  outRow.className = 'row';
  const flattenButton = button('Flatten');
  const cancelButton = button('Cancel orders');
  outRow.append(flattenButton, cancelButton);

  const log = el('div', '', 'log');
  root.append(state, pinRow, sizeRow, sendRow, outRow, log);

  const draw = (): void => {
    const ctx = context();
    const why = blockedWhy(status, ctx != null);
    const buyWhy = why == null ? buyBlockedWhy(ctx) : null;
    const unlocked = Boolean(status?.unlocked);
    state.textContent = why ?? buyWhy ?? `Unlocked · desk on Paper · padlock ${status?.armed ? 'open' : 'closed (a buy is refused until it is open)'}`;
    pinInput.hidden = unlocked;
    unlockButton.textContent = unlocked ? 'Lock phone' : 'Unlock';
    unlockButton.disabled = busy || !status?.pin_set;
    padlockButton.textContent = status?.armed ? 'Close padlock' : 'Open padlock';
    padlockButton.disabled = busy || !unlocked;
    for (const b of [sellButton, flattenButton, cancelButton]) b.disabled = busy || why != null;
    buyButton.disabled = busy || why != null || buyWhy != null;
    log.replaceChildren(...lines.map((line) => {
      const row = el('div', line.text);
      if (!line.ok) row.className = 'no';
      return row;
    }));
  };

  const refresh = async (): Promise<void> => {
    status = await door.status();
    draw();
  };

  /** Run one tap: nothing else may be tapped until Nova answers, so a slow answer is never doubled. */
  const tap = async (label: string, send: () => Promise<Answer>): Promise<void> => {
    if (busy) return;
    busy = true;
    draw();
    const answer = await send();
    if (answer.status) status = answer.status;
    lines.unshift({ ok: answer.ok, text: `${label} · ${Math.round(answer.ms)} ms · ${answer.ok ? '' : 'refused: '}${answer.text}` });
    lines.length = Math.min(lines.length, LOG_KEEP);
    busy = false;
    await refresh();
  };

  const sized = (): { qty: number; limit: number | null } | string => {
    const qty = Number(qtyInput.value);
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isInteger(qty)) return 'Enter a whole number of shares.';
    const raw = priceInput.value.trim();
    if (!raw) return { qty, limit: null };
    const limit = Number(raw);
    if (!Number.isFinite(limit) || limit <= 0) return 'The limit price is not a price.';
    return { qty, limit };
  };

  const send = (side: 'BUY' | 'SELL'): void => {
    const ctx = context();
    const size = sized();
    if (!ctx) return;
    if (typeof size === 'string') {
      lines.unshift({ ok: false, text: size });
      draw();
      return;
    }
    const what = `${side === 'BUY' ? 'Buy' : 'Sell'} ${size.qty} ${ctx.symbol} ${size.limit == null ? 'at market' : `at ${size.limit}`}`;
    void tap(what, () => door.order(ctx, side, size.qty, size.limit));
  };

  unlockButton.addEventListener('click', () => {
    if (status?.unlocked) {
      void tap('Lock phone', () => door.lock());
      return;
    }
    const pin = pinInput.value;
    pinInput.value = '';
    void tap('Unlock', () => door.unlock(pin));
  });
  padlockButton.addEventListener('click', () => {
    const open = !status?.armed;
    void tap(open ? 'Open padlock' : 'Close padlock', () => door.arm(open));
  });
  buyButton.addEventListener('click', () => send('BUY'));
  sellButton.addEventListener('click', () => send('SELL'));
  flattenButton.addEventListener('click', () => {
    const ctx = context();
    if (ctx) void tap(`Flatten ${ctx.symbol}`, () => door.flatten(ctx));
  });
  cancelButton.addEventListener('click', () => {
    const ctx = context();
    if (ctx) void tap(`Cancel orders on ${ctx.symbol}`, () => door.cancelSymbol(ctx.symbol));
  });

  void refresh();
  // The buttons follow the test: Buy opens when the first Level 2 book arrives, with no tap needed.
  window.setInterval(() => { if (!document.hidden) draw(); }, 1_000);
  window.setInterval(() => { if (!busy && !document.hidden) void refresh(); }, STATUS_EVERY_MS);
  return root;
}
