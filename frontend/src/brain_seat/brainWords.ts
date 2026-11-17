/**
 * The brain in words (ADR 072, approved mockup brain-switches v1 sections 1-2), pure: what its header pill says in
 * each state, and its panel's rows. Nothing here reads the network.
 *
 * The pill, first that applies:
 *   Brain · Done for today -$500             its day stop was reached (red)
 *   Brain · Off · XLAB is yours to close     Off, and it handed you a trade (amber)
 *   Brain · Off                              Off (muted)
 *   Brain · On · its program is not running  On, and its program has not checked in (amber; never a silent block)
 *   Brain · In XLAB +$42.00                  On, in a trade
 *   Brain · Buy set SSII                     On, an entry working
 *   Brain · Watching SSII / Brain · Watching On, reading
 */
import type { BrainSeatLane, BrainSeatStatus } from './types';

export type BrainTone = 'off' | 'on' | 'wait' | 'done';
export type BrainPnlTone = 'up' | 'dn' | 'flat';

export interface BrainPnl {
  text: string;
  tone: BrainPnlTone;
}

export interface BrainPillWords {
  tone: BrainTone;
  /** The bold start: "Brain", "Brain · Off", "Brain · On". */
  lead: string;
  /** The muted words after it ("· Watching SSII"); null when the lead says it all. */
  rest: string | null;
  /** The figure at the end: the open trade's P&L, or the day's once it is done. */
  pnl: BrainPnl | null;
}

export const BRAIN_NAME = 'Brain';
export const BRAIN_PANEL_LABEL = 'The brain';
export const BRAIN_NOT_RUNNING = 'its program is not running';
export const BRAIN_NOT_RUNNING_TIP = "The brain's program has not checked in, so it makes no new trade. Its stop and "
  + 'target keep resting, flat by still closes it, and nothing in Nova restarts it.';

export function fmtPrice(p: number): string {
  return Math.abs(p) < 1 ? p.toFixed(4) : p.toFixed(2);
}

export function fmtQty(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

/** "+$42.00", "-$120.00", "$0.00". */
export function fmtMoney(v: number): string {
  const sign = v < 0 ? '-' : v > 0 ? '+' : '';
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Whole dollars, signed only when it is a loss: "-$500", "$150". */
export function fmtWhole(v: number): string {
  const whole = Math.round(Math.abs(v));
  return `${v < 0 && whole > 0 ? '-' : ''}$${whole.toLocaleString('en-US')}`;
}

const pnlTone = (v: number): BrainPnlTone => (v > 0 ? 'up' : v < 0 ? 'dn' : 'flat');

export function etClock(epochSec: number): string {
  return new Date(epochSec * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit',
  });
}

/** What the pill says (the header's states, mockup section 1). */
export function brainPillWords(status: BrainSeatStatus): BrainPillWords {
  if (status.state === 'done' || status.done_for_today) {
    const pnl = status.today.pnl;
    // The day's figure in whole dollars with its sign, as the mockup writes it ("-$500").
    const figure = pnl === null ? null : { text: `${pnl > 0 ? '+' : ''}${fmtWhole(pnl)}`, tone: pnlTone(pnl) };
    return { tone: 'done', lead: BRAIN_NAME, rest: '· Done for today', pnl: figure };
  }
  if (!status.on) {
    const handed = status.handed[0];
    return handed
      ? { tone: 'wait', lead: `${BRAIN_NAME} · Off`, rest: `· ${handed.symbol} is yours to close`, pnl: null }
      : { tone: 'off', lead: `${BRAIN_NAME} · Off`, rest: null, pnl: null };
  }
  if (status.connected === false) {
    return { tone: 'wait', lead: `${BRAIN_NAME} · On`, rest: `· ${BRAIN_NOT_RUNNING}`, pnl: null };
  }
  const position = status.position;
  if (position) {
    const pnl = position.unrealized_pnl;
    return {
      tone: 'on', lead: BRAIN_NAME, rest: `· In ${position.symbol}`,
      pnl: pnl === null ? null : { text: fmtMoney(pnl), tone: pnlTone(pnl) },
    };
  }
  const symbol = status.lane.symbol ?? status.symbol;
  if (status.state === 'in_trade' && symbol) return { tone: 'on', lead: BRAIN_NAME, rest: `· In ${symbol}`, pnl: null };
  if (status.state === 'buy_set' && symbol) return { tone: 'on', lead: BRAIN_NAME, rest: `· Buy set ${symbol}`, pnl: null };
  return { tone: 'on', lead: BRAIN_NAME, rest: symbol ? `· Watching ${symbol}` : '· Watching', pnl: null };
}

/** The pill's words without its figure -- the panel's title: "Brain · In XLAB". */
export function brainPillTitle(words: BrainPillWords): string {
  return words.rest ? `${words.lead} ${words.rest}` : words.lead;
}

/** The whole pill as one line: "Brain · In XLAB +$42.00". */
export function brainPillText(words: BrainPillWords): string {
  return words.pnl ? `${brainPillTitle(words)} ${words.pnl.text}` : brainPillTitle(words);
}

const VENUE_NAMES: Record<string, string> = { paper: 'Paper', sim: 'Sim', live: 'Live' };

/** The panel's line under its title: "Paper · lane 3". */
export function brainSubLine(venue: string | null): string {
  const name = venue ? VENUE_NAMES[venue] ?? venue : null;
  return name ? `${name} · lane 3` : 'Lane 3';
}

/** "The brain, 10:41" (ET) over its note. */
export function brainNoteHead(at: number): string {
  return at > 0 ? `The brain, ${etClock(at)}` : 'The brain';
}

/** A row's words around one ticker: `before` + the ticker + `after`; no ticker when `symbol` is null. */
export interface BrainSymbolWords {
  before: string;
  symbol: string | null;
  after: string;
}

/** The panel's "Lane" row. */
export function brainLaneRow(lane: BrainSeatLane): BrainSymbolWords {
  if (!lane.symbol) return { before: 'No stock yet', symbol: null, after: '' };
  if (!lane.depth) return { before: 'Waiting for ', symbol: lane.symbol, after: "'s Level 2" };
  return { before: 'Level 2 + Time & Sales on ', symbol: lane.symbol, after: '' };
}

/** The panel's "Position" row in its parts: the figures are set in mono, the ticker opens its Trader tab. */
export interface BrainPositionRow {
  /** A short says so before its size. */
  short: boolean;
  qty: string;
  symbol: string;
  /** Its average cost; null when the answer has none, or for a handed trade. */
  at: string | null;
  /** Its mark now; null when the answer has none, or for a handed trade. */
  now: string | null;
  /** The brain handed it to you while Off: yours to close. */
  handed: boolean;
  /** A handed trade's resting stop; null with none resting. */
  stop: string | null;
}

export const BRAIN_POSITION_NONE = 'None';
export const BRAIN_POSITION_HANDED = 'yours to close';

/** The brain's open trade, else the trade it handed you while Off; null with neither. */
export function brainPositionRow(status: BrainSeatStatus): BrainPositionRow | null {
  const p = status.position;
  if (p) {
    return {
      short: p.qty < 0, qty: fmtQty(Math.abs(p.qty)), symbol: p.symbol,
      at: p.avg_cost === null ? null : fmtPrice(p.avg_cost), now: p.mark === null ? null : fmtPrice(p.mark),
      handed: false, stop: null,
    };
  }
  const h = status.handed[0];
  if (!h) return null;
  return {
    short: h.qty < 0, qty: fmtQty(Math.abs(h.qty)), symbol: h.symbol, at: null, now: null, handed: true,
    stop: h.stop_price === null ? null : fmtPrice(h.stop_price),
  };
}

/** The row as one line: "200 XLAB at 4.32 · now 4.53", "200 XLAB · yours to close · stop 4.19", "None". */
export function brainPositionText(row: BrainPositionRow | null): string {
  if (!row) return BRAIN_POSITION_NONE;
  return `${row.short ? 'Short ' : ''}${row.qty} ${row.symbol}${row.at ? ` at ${row.at}` : ''}`
    + `${row.now ? ` · now ${row.now}` : ''}${row.handed ? ` · ${BRAIN_POSITION_HANDED}` : ''}`
    + `${row.stop ? ` · stop ${row.stop}` : ''}`;
}

export interface BrainTodayRow {
  /** "+$42.00"; null when the day's P&L is not known. */
  pnl: BrainPnl | null;
  /** How far the day's loss has come toward the day stop, 0 to 1; null with no day stop. */
  meter: number | null;
  /** "day stop -$500"; null with no day stop. */
  stop: string | null;
}

export const BRAIN_PNL_UNKNOWN = 'P&L unknown';

/** The panel's "Today" row: the day's P&L, the meter filling as the loss nears the day stop, and the stop. */
export function brainTodayRow(status: BrainSeatStatus): BrainTodayRow {
  const { pnl, loss_limit_usd: limit } = status.today;
  const stopUsd = limit === null ? null : Math.abs(limit);
  const lost = pnl !== null && pnl < 0 ? -pnl : 0;
  return {
    pnl: pnl === null ? null : { text: fmtMoney(pnl), tone: pnlTone(pnl) },
    meter: stopUsd === null || stopUsd <= 0 ? null : Math.min(1, lost / stopUsd),
    stop: stopUsd === null ? null : `day stop ${fmtWhole(-stopUsd)}`,
  };
}

/** One limit: its figure (mono) and its unit. */
export interface BrainLimit {
  figure: string;
  unit: string;
}

/** The panel's "Limits" row before its Settings link: "1,000 sh · $150 risk · -$500 day". */
export function brainLimitsRow(status: BrainSeatStatus): BrainLimit[] {
  const out: BrainLimit[] = [];
  const { max_shares: shares, risk_usd: risk } = status.limits;
  const day = status.today.loss_limit_usd;
  if (shares !== null) out.push({ figure: fmtQty(shares), unit: 'sh' });
  if (risk !== null) out.push({ figure: fmtWhole(risk), unit: 'risk' });
  if (day !== null) out.push({ figure: fmtWhole(-Math.abs(day)), unit: 'day' });
  return out;
}

export const BRAIN_READING_HEAD = 'Reading now';
export const BRAIN_READING_LANE = 'its lane';
export const BRAIN_READING_LEVEL1 = 'Level 1';
export const BRAIN_SETTINGS_LINK = 'Settings';

/** The panel's foot: a bold lead ("Off:") and what the switch does next, or the refusal On would meet. */
export interface BrainHelp {
  lead: string | null;
  text: string;
}

export const BRAIN_OFF_HELP_GENERIC = 'no new trades. Its working entries are cancelled. Its open trade and its stop '
  + 'stay as they are, and the trade is yours to close.';
export const BRAIN_ON_HELP = 'the brain may trade again. A trade it handed you stays yours until you close it.';
export const brainOffHelp = (symbol: string | null): string => (symbol
  ? `no new trades. Its working entries are cancelled. ${symbol} and its stop stay as they are, and ${symbol} is yours to close.`
  : BRAIN_OFF_HELP_GENERIC);

/** "Off: no new trades. ... XLAB is yours to close." while On; while Off, why On is refused or what On does. */
export function brainHelp(status: BrainSeatStatus): BrainHelp {
  if (status.on) return { lead: 'Off:', text: brainOffHelp(status.position?.symbol ?? null) };
  if (status.why_not_on) return { lead: null, text: status.why_not_on.error };
  return { lead: 'On:', text: BRAIN_ON_HELP };
}

/** The tag on the Trader's Level 2 frame while the pane's stock is the brain's lane's. */
export const BRAIN_LINE_TAG = "The brain's line · you share it";

export const BRAIN_WHY_BUSY ='Waiting for Nova to answer your last press.';
export const BRAIN_SWITCH_LABEL = "The brain's switch";
export const BRAIN_SWITCH_ON = 'On';
export const BRAIN_SWITCH_OFF = 'Off';

/** What pressing the switch does, for its tip: the refusal On would meet, else the flip. */
export function brainSwitchTip(status: BrainSeatStatus, busy: boolean): string {
  if (busy) return BRAIN_WHY_BUSY;
  const help = brainHelp(status);
  if (status.on) return `${BRAIN_SWITCH_LABEL}: On. ${help.lead} ${help.text}`;
  return help.lead ? `${BRAIN_SWITCH_LABEL}: Off. ${help.lead} ${help.text}` : help.text;
}
