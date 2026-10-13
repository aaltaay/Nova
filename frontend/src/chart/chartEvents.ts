/**
 * Earnings reports and splits on the daily charts (operator ask, 2026-10-12): the wire shape of
 * `GET /api/chart-events/{symbol}`, which candle each event's mark sits on, and the words of its card.
 *
 * The backend reads them (`backend/chart_events/`): earnings from SEC EDGAR -- the day results came out, the
 * fiscal period and the report's own revenue, net income and EPS -- and splits from Massive's list, the splits
 * SEC filings confirmed and Yahoo's history. Nothing here estimates: a figure nobody tagged says so, and a
 * list that could not be read is named.
 */
import type { Time } from 'lightweight-charts';
import { toCanonicalTime } from './chartDrawingTime';
import { CHART_EVENT_DAILY_SNAP_DAYS, CHART_EVENT_SAID_CHARS } from './chartEventConstants';

export interface ChartFigure {
  value: number;
  unit: string;
  /** The filing that tagged it, and when. */
  form: string | null;
  filed: string | null;
}

export interface FilingStamp {
  form: string;
  accession: string;
  /** The day it counts for: a release's own day (the company's, or an 8-K's date of event). */
  day: string;
  /** The day SEC dated it. */
  filed: string;
}

export interface EarningsEvent {
  kind: 'earnings';
  id: string;
  day: string;
  /** The 8-K Item 2.02 or results 6-K that brought the results out, when one did. */
  release: FilingStamp | null;
  /** Other releases in the report's window: a preliminary, a second results filing. Listed, never marked. */
  otherReleases: FilingStamp[];
  /** The 10-Q / 10-K / 20-F / 40-F / XBRL 6-K that reported them; null when none has (yet). */
  report: FilingStamp | null;
  reportPending: boolean;
  /** The results 6-K's own sentence. */
  said: string | null;
  periodLabel: string | null;
  periodEnd: string | null;
  periodMonths: number | null;
  revenue: ChartFigure | null;
  netIncome: ChartFigure | null;
  eps: ChartFigure | null;
}

export interface SplitEvent {
  kind: 'split';
  id: string;
  day: string;
  ratio: number;
  newShares: number | null;
  oldShares: number | null;
  reverse: boolean;
  sources: string[];
  disagreement: string | null;
}

export type ChartEvent = EarningsEvent | SplitEvent;

export interface ChartEventsRead {
  symbol: string;
  /** Still reading: nothing kept yet, or a foreign issuer's 6-Ks being read. */
  busy: boolean;
  events: ChartEvent[];
  /** What could not be read, in words; empty when every source answered. */
  notes: string[];
  /** How far back a foreign issuer's results are read (its 6-Ks); null for every other registrant. */
  coverage: string | null;
}

export const EMPTY_CHART_EVENTS: ChartEventsRead = { symbol: '', busy: false, events: [], notes: [], coverage: null };

type Raw = Record<string, unknown>;
const isObj = (v: unknown): v is Raw => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const DAY = /^\d{4}-\d{2}-\d{2}$/;

function stamp(v: unknown): FilingStamp | null {
  if (!isObj(v)) return null;
  const form = str(v.form);
  const day = str(v.day);
  const filed = str(v.filed);
  return form && day && DAY.test(day)
    ? { form, accession: str(v.accession) ?? '', day, filed: filed && DAY.test(filed) ? filed : day } : null;
}

function figure(v: unknown): ChartFigure | null {
  if (!isObj(v)) return null;
  const value = num(v.value);
  const unit = str(v.unit);
  return value != null && unit ? { value, unit, form: str(v.form), filed: str(v.filed) } : null;
}

function event(v: unknown): ChartEvent | null {
  if (!isObj(v)) return null;
  const id = str(v.id);
  const day = str(v.day);
  if (!id || !day || !DAY.test(day)) return null;
  if (v.kind === 'split') {
    const ratio = num(v.ratio);
    if (ratio == null || ratio <= 0) return null;
    return {
      kind: 'split', id, day, ratio,
      newShares: num(v.new_shares), oldShares: num(v.old_shares), reverse: v.reverse === true,
      sources: Array.isArray(v.sources) ? v.sources.filter((s): s is string => typeof s === 'string') : [],
      disagreement: str(v.disagreement),
    };
  }
  if (v.kind !== 'earnings') return null;
  return {
    kind: 'earnings', id, day,
    release: stamp(v.release),
    otherReleases: Array.isArray(v.other_releases)
      ? v.other_releases.map(stamp).filter((s): s is FilingStamp => s !== null) : [],
    report: stamp(v.report),
    reportPending: v.report_pending === true,
    said: str(v.said),
    periodLabel: str(v.period_label),
    periodEnd: str(v.period_end),
    periodMonths: num(v.period_months),
    revenue: figure(v.revenue),
    netIncome: figure(v.net_income),
    eps: figure(v.eps),
  };
}

const LIST_NAMES: Record<string, string> = { massive: 'Massive', sec_confirmed: 'SEC-confirmed', yahoo: 'Yahoo' };

/** The route's answer as the pane uses it; anything malformed is left out, never guessed. */
export function normalizeChartEvents(raw: unknown, symbol: string): ChartEventsRead {
  if (!isObj(raw)) return { ...EMPTY_CHART_EVENTS, symbol };
  const notes: string[] = [];
  const events: ChartEvent[] = [];
  let coverage: string | null = null;
  let busy = raw.status === 'reading';
  const earnings = isObj(raw.earnings) ? raw.earnings : null;
  const splits = isObj(raw.splits) ? raw.splits : null;
  if (raw.status === 'off') notes.push('Earnings and split marks are off on this desk (NOVA_CHART_EVENTS=0).');
  if (raw.status === 'error') notes.push(`Earnings and splits could not be read: ${str(raw.error) ?? 'no reason given'}.`);
  if (earnings) {
    for (const e of Array.isArray(earnings.events) ? earnings.events : []) {
      const ev = event(e);
      if (ev?.kind === 'earnings') events.push(ev);
    }
    if (earnings.status === 'error') notes.push(`SEC filings could not be read (${str(earnings.error) ?? 'no reason given'}).`);
    else if (earnings.status === 'no_cik') notes.push('SEC lists no registrant under this symbol: no earnings marks.');
    else if (str(earnings.error)) notes.push(`SEC: ${str(earnings.error)}.`);
    const scan = isObj(earnings.scan) ? earnings.scan : null;
    if (scan && (num(scan.pending) ?? 0) > 0) busy = true;
    const known = str(earnings.releases_known_since);
    if (earnings.foreign_6k === true && known) {
      coverage = `Results filed on Form 6-K are read from ${dayWords(known)}; earlier reports are not marked.`;
    }
  }
  if (splits) {
    for (const e of Array.isArray(splits.events) ? splits.events : []) {
      const ev = event(e);
      if (ev?.kind === 'split') events.push(ev);
    }
    const lists = isObj(splits.lists) ? splits.lists : {};
    for (const [key, state] of Object.entries(lists)) {
      if (isObj(state) && state.status === 'error') {
        notes.push(`${LIST_NAMES[key] ?? key} split list could not be read (${str(state.error) ?? 'no reason given'}).`);
      }
    }
  }
  events.sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : a.kind.localeCompare(b.kind)));
  return { symbol, busy, events, notes, coverage };
}

/** A daily+ series time as its calendar day, `YYYY-MM-DD`. */
export function seriesDay(time: Time): string | null {
  const epoch = toCanonicalTime(time);
  return Number.isFinite(epoch) ? new Date(epoch * 1000).toISOString().slice(0, 10) : null;
}

const dayMs = (day: string) => Date.parse(`${day}T00:00:00Z`);

export interface PlacedEvent {
  event: ChartEvent;
  time: Time;
}

/**
 * The candle each event's mark sits on. On a daily chart, the first candle on or after its day (a filing
 * made on a Saturday reaches Monday's candle), never more than `CHART_EVENT_DAILY_SNAP_DAYS` past it; on a
 * weekly or monthly chart, the candle whose week or month holds the day. An event past the newest candle --
 * a Sim replay's own day, or after it -- has no mark.
 */
export function placeEvents(events: readonly ChartEvent[], times: readonly Time[], timeframe: string): PlacedEvent[] {
  const days = times.map((t) => ({ time: t, day: seriesDay(t) })).filter((b): b is { time: Time; day: string } => !!b.day);
  if (days.length === 0) return [];
  const out: PlacedEvent[] = [];
  for (const ev of events) {
    if (timeframe === '1Day') {
      const hit = days.find((b) => b.day >= ev.day);
      if (hit && dayMs(hit.day) - dayMs(ev.day) <= CHART_EVENT_DAILY_SNAP_DAYS * 86_400_000) out.push({ event: ev, time: hit.time });
      continue;
    }
    let idx = -1;
    for (let i = 0; i < days.length && days[i].day <= ev.day; i += 1) idx = i;
    if (idx < 0) continue;
    const start = days[idx].day;
    const end = idx + 1 < days.length ? days[idx + 1].day : periodEnd(start, timeframe);
    if (ev.day < end) out.push({ event: ev, time: days[idx].time });
  }
  return out;
}

function periodEnd(start: string, timeframe: string): string {
  const d = new Date(dayMs(start));
  if (timeframe === '1Month') return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1)).toISOString().slice(0, 10);
  return new Date(dayMs(start) + 7 * 86_400_000).toISOString().slice(0, 10);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Mar 12, 2026". */
export function dayWords(day: string | null): string {
  if (!day || !DAY.test(day)) return '—';
  const [y, m, d] = day.split('-').map(Number);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

/** "3.95M", "-12.31M", "1.42B", "950.0K": money at the precision a report states it. */
export function moneyWords(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

const currency = (unit: string) => unit.split('/')[0];

export interface CardRow {
  label: string;
  value: string;
  /** A short line under the value: where a figure came from. */
  note?: string;
  warn?: boolean;
}

export interface EventCard {
  title: string;
  color: 'earnings' | 'split';
  rows: CardRow[];
  /** Quoted words and the source, under the rows. */
  quote: string | null;
  source: string;
  /** A foreign issuer's 6-K coverage, under the source. */
  coverage: string | null;
}

/** "1 for 6", "3 for 2"; a stock dividend's ratio as a ratio. */
export function splitWords(ev: SplitEvent): string {
  if (ev.newShares && ev.oldShares) return `${ev.newShares} for ${ev.oldShares}`;
  return `${Number(ev.ratio.toPrecision(4))} for 1`;
}

function figureRow(label: string, fig: ChartFigure | null, eventDay: string, reportDay: string | null,
  format: (v: number) => string): CardRow | null {
  if (!fig) return null;
  const own = fig.filed === reportDay || fig.filed === eventDay;
  return {
    label,
    value: `${format(fig.value)} ${currency(fig.unit)}`,
    note: own || !fig.filed ? undefined : `as tagged in the ${fig.form ?? 'filing'} of ${dayWords(fig.filed)}`,
  };
}

function periodWords(ev: EarningsEvent): string | null {
  const span = ev.periodMonths && ev.periodEnd ? `${ev.periodMonths} months to ${dayWords(ev.periodEnd)}` : null;
  if (ev.periodLabel && span) return `${ev.periodLabel} · ${span}`;
  return ev.periodLabel ?? span;
}

/** The card a mark opens: Webull's Date / Period / Revenue, with where each word came from. */
export function eventCard(ev: ChartEvent, coverage: string | null = null): EventCard {
  if (ev.kind === 'split') {
    const rows: CardRow[] = [
      { label: 'Date', value: dayWords(ev.day) },
      { label: ev.reverse ? 'Reverse split' : 'Split', value: splitWords(ev) },
    ];
    if (ev.disagreement) rows.push({ label: 'Note', value: ev.disagreement, warn: true });
    return {
      title: ev.reverse ? 'Reverse split' : 'Stock split', color: 'split', rows, quote: null,
      source: `Listed by ${ev.sources.map((s) => LIST_NAMES[s] ?? s).join(' · ') || 'no list'}`, coverage: null,
    };
  }
  const rows: CardRow[] = [{ label: 'Date', value: dayWords(ev.day) }];
  const period = periodWords(ev);
  if (period) rows.push({ label: 'Period', value: period });
  const reportDay = ev.report?.day ?? null;
  const figures = [
    figureRow('Revenue', ev.revenue, ev.day, reportDay, moneyWords),
    figureRow('Net income', ev.netIncome, ev.day, reportDay, moneyWords),
    figureRow('EPS', ev.eps, ev.day, reportDay, (v) => v.toFixed(2)),
  ].filter((r): r is CardRow => r !== null);
  rows.push(...figures);
  if (figures.length === 0) {
    rows.push({ label: 'Figures', value: ev.reportPending ? 'in no filing yet' : 'none tagged in SEC filings' });
  }
  if (ev.release) {
    const late = ev.release.filed !== ev.release.day ? `filed ${dayWords(ev.release.filed)}` : undefined;
    rows.push({ label: 'Released', value: `${ev.release.form} · ${dayWords(ev.release.day)}`, note: late });
  }
  if (ev.report) rows.push({ label: 'Report', value: `${ev.report.form} · ${dayWords(ev.report.day)}` });
  else if (ev.reportPending) rows.push({ label: 'Report', value: 'not filed yet' });
  if (ev.otherReleases.length > 0) {
    rows.push({ label: 'Also filed', value: ev.otherReleases.map((r) => `${r.form} · ${dayWords(r.day)}`).join(', ') });
  }
  const quote = ev.said ? (ev.said.length > CHART_EVENT_SAID_CHARS ? `${ev.said.slice(0, CHART_EVENT_SAID_CHARS)}…` : ev.said) : null;
  return { title: 'Earnings', color: 'earnings', rows, quote, source: 'SEC EDGAR', coverage };
}
