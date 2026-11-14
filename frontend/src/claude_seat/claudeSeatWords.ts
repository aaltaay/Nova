/**
 * Claude's seat in words and lines (ADR 068), pure: the pill's tone, the panel's rows, the lines a chart pane
 * draws for Claude's orders and armed breaks, and which events pop a toast. Nothing here reads the network.
 */
import type { ClaudeBreak, ClaudeEvent, ClaudeOrder, ClaudeSeatState, ClaudeSeatStatus, ClaudeSwitch } from './types';

export type ClaudeTone = 'off' | 'wait' | 'on' | 'done';

export function seatTone(state: ClaudeSeatState): ClaudeTone {
  if (state === 'off') return 'off';
  if (state === 'waiting_line') return 'wait';
  if (state === 'done') return 'done';
  return 'on';
}

/**
 * The pill's tone: muted while the operator's switch is Off (ADR 072) -- Claude makes no new trade then, whatever it
 * watches -- red once its day is done, amber while it holds shares without a Level 2.
 */
export function pillTone(status: ClaudeSeatStatus): ClaudeTone {
  if (status.state === 'done') return 'done';
  if (status.switch && !status.switch.on) return 'off';
  if (status.state === 'in_trade' && !status.line.depth) return 'wait';
  return seatTone(status.state);
}

export function fmtPrice(p: number): string {
  return Math.abs(p) < 1 ? p.toFixed(4) : p.toFixed(2);
}

export function fmtQty(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

export function fmtMoney(v: number): string {
  const sign = v < 0 ? '-' : v > 0 ? '+' : '';
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function etClock(epochSec: number, seconds = false): string {
  return new Date(epochSec * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit',
    ...(seconds ? { second: '2-digit' } : {}),
  });
}

/**
 * The pill shows whenever the desk has read the seat: what Claude is doing while it is on, "Claude · Off" (muted)
 * while it is off -- every day, so the operator sees Claude is off (operator, 2026-10-30).
 */
export function pillShown(status: ClaudeSeatStatus | null): boolean {
  return status != null;
}

export type ClaudeLineKind = 'buy' | 'sell' | 'stop';

export interface ClaudeChartLine {
  id: string;
  price: number;
  kind: ClaudeLineKind;
  /** "Claude · buy 510 on a print at 4.39 (up to 4.41)". */
  label: string;
}

function orderLine(o: ClaudeOrder): ClaudeChartLine | null {
  const id = `order-${o.order_id}`;
  const qty = fmtQty(o.qty);
  if (o.leg_role === 'stop' || ((o.order_type ?? '').toUpperCase() === 'STP' && o.side === 'SELL')) {
    return o.stop_price === null ? null
      : { id, price: o.stop_price, kind: 'stop', label: `Claude · stop ${qty} at ${fmtPrice(o.stop_price)}` };
  }
  if (o.limit_price === null) return null;
  if (o.side === 'BUY') {
    return { id, price: o.limit_price, kind: 'buy', label: `Claude · buy ${qty} at ${fmtPrice(o.limit_price)}` };
  }
  return { id, price: o.limit_price, kind: 'sell', label: `Claude · sell ${qty} at ${fmtPrice(o.limit_price)}` };
}

function breakLines(b: ClaudeBreak): ClaudeChartLine[] {
  const qty = fmtQty(b.qty);
  const out: ClaudeChartLine[] = [
    { id: `break-${b.id}-buy`, price: b.trigger, kind: 'buy',
      label: `Claude · buy ${qty} on a print at ${fmtPrice(b.trigger)} (up to ${fmtPrice(b.top)})` },
    { id: `break-${b.id}-stop`, price: b.stop, kind: 'stop', label: `Claude · stop ${qty} at ${fmtPrice(b.stop)}` },
  ];
  if (b.target2 !== null && b.target1_qty !== null && b.target1_qty > 0 && b.target1_qty < b.qty) {
    out.push({ id: `break-${b.id}-t1`, price: b.target, kind: 'sell',
      label: `Claude · sell ${fmtQty(b.target1_qty)} at ${fmtPrice(b.target)}` });
    out.push({ id: `break-${b.id}-t2`, price: b.target2, kind: 'sell',
      label: `Claude · sell ${fmtQty(b.qty - b.target1_qty)} at ${fmtPrice(b.target2)}` });
  } else {
    out.push({ id: `break-${b.id}-t1`, price: b.target, kind: 'sell', label: `Claude · sell ${qty} at ${fmtPrice(b.target)}` });
  }
  return out;
}

/** The lines a chart of ``symbol`` draws for Claude: its working orders there and its armed breaks. */
export function claudeChartLines(status: ClaudeSeatStatus | null, symbol: string): ClaudeChartLine[] {
  if (!status || !symbol) return [];
  const sym = symbol.toUpperCase();
  const lines = status.working.filter(o => o.symbol === sym).map(orderLine)
    .filter((l): l is ClaudeChartLine => l !== null);
  for (const b of status.breaks) if (b.symbol === sym) lines.push(...breakLines(b));
  return lines;
}

/** Events that pop a toast and that the desk's voice says; the switch's own (ADR 072) included. */
export const CLAUDE_TOAST_KINDS: ReadonlySet<string> = new Set([
  'buy_set', 'break_set', 'fill', 'reflex_fired', 'close', 'day_close', 'refused', 'line_wait', 'off',
  'switch_off', 'handed',
]);

/** Events whose words are a whole sentence already ("Claude is off: its 300 SMPL are yours to close."). */
const AS_WRITTEN: ReadonlySet<string> = new Set(['switch_off', 'handed']);

/** "Claude set buy 510 SMPL ..." -- the event's own words after the name; the switch's sentences as written. */
export function eventWords(e: ClaudeEvent): string {
  return AS_WRITTEN.has(e.kind) ? e.text : `Claude ${e.text}`;
}

/** Events newer than ``since`` that toast, oldest first. */
export function freshToasts(events: ClaudeEvent[], since: number): ClaudeEvent[] {
  return events.filter(e => e.at > since && CLAUDE_TOAST_KINDS.has(e.kind)).sort((a, b) => a.at - b.at);
}

/** The panel's "Buy set" row: the armed break or the resting buy, with its risk. */
export function buySetRow(status: ClaudeSeatStatus): string | null {
  const b = status.breaks[0];
  if (b) {
    const risk = (b.top - b.stop) * b.qty;
    return `${fmtQty(b.qty)} over ${fmtPrice(b.trigger)} · risk $${Math.round(risk)} · ends ${etClock(b.expires_at)}`;
  }
  const entry = status.working.find(o => o.side === 'BUY' && (o.leg_role === 'parent' || o.leg_role === null));
  if (!entry || entry.limit_price === null) return null;
  const stop = status.working.find(o => o.leg_role === 'stop' && o.parent_id === entry.order_id);
  const risk = stop?.stop_price != null ? ` · risk $${Math.round((entry.limit_price - stop.stop_price) * entry.qty)}` : '';
  return `${fmtQty(entry.qty)} at ${fmtPrice(entry.limit_price)}${risk}`;
}

/** The panel's "My line" row. */
export function lineRow(status: ClaudeSeatStatus): string {
  const l = status.line;
  // Claude's own lane (ADR 071): one of the three lines, never yours or the bots'.
  if (l.symbol && l.depth) return `Level 2 + Time & Sales on ${l.symbol} · Claude's lane`;
  if (status.state === 'waiting_line') return l.why_not ?? 'Waiting for a Level 2 line';
  return 'None yet';
}

/** The panel's "Today" row. */
export function todayRow(status: ClaudeSeatStatus): string {
  const t = status.today;
  const pnl = t.pnl === null ? 'P&L unknown' : fmtMoney(t.pnl);
  const stop = t.day_stop === null ? '' : ` · I stop for the day at -$${Math.abs(Math.round(t.day_stop))}`;
  // No daily trade count unless one is set (operator, 2026-10-27).
  const count = t.max_entries === null ? `${t.entries} · no cap` : `${t.entries} of ${t.max_entries}`;
  return `Trades ${count} · ${pnl}${stop}`;
}

export const CLAUDE_WHY_BUSY = 'Waiting for Nova to answer your last press.';
/** The switch's words (approved mockup brain-switches v1, section 1-2). */
export const CLAUDE_SWITCH_LABEL = "Claude's switch";
export const CLAUDE_SWITCH_ON = 'On';
export const CLAUDE_SWITCH_OFF = 'Off';
export const CLAUDE_SWITCH_OFF_HELP = 'Off: no new trades. Its working entries are cancelled. Its open trade and its stop '
  + 'stay as they are, and the trade is yours to close.';
export const CLAUDE_SWITCH_ON_HELP = 'On: Claude may trade on Paper again. A trade it handed you stays yours until you close it.';

/** What pressing the switch does, for its tip: the refusal On would meet, else the flip. */
export function switchTip(sw: ClaudeSwitch, busy: boolean): string {
  if (busy) return CLAUDE_WHY_BUSY;
  if (sw.on) return `${CLAUDE_SWITCH_LABEL}: On. ${CLAUDE_SWITCH_OFF_HELP}`;
  return sw.why_not_on?.error ?? `${CLAUDE_SWITCH_LABEL}: Off. ${CLAUDE_SWITCH_ON_HELP}`;
}

/** "checked in 40 s ago" from the lease's last beat. */
export function checkedIn(status: ClaudeSeatStatus, nowSec = Date.now() / 1000): string | null {
  if (status.beat_at === null) return null;
  const ago = Math.max(0, Math.round(nowSec - status.beat_at));
  return ago < 90 ? `checked in ${ago} s ago` : `checked in ${Math.round(ago / 60)} min ago`;
}
