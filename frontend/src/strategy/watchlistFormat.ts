/** Pure helpers for the Watchlist table: pillar letters, the News and Setup cells, filters, the summary line. */
import {
  CATALYST_CATEGORY_LABELS,
  CATALYST_CATEGORY_SHORT,
  CATALYST_VERDICT_TITLES,
  WATCHLIST_PILLAR_LETTERS,
} from '../constants';
import { rowRank, setupShort, setupTypeOf, stateWords, type SetupRow } from '../setups';
import type { WatchlistEntry } from './types';

export type WatchlistFilter = 'all' | 'pillars5' | 'setup_live' | 'allowlist';

/** A setup still in play: its trigger can still print. */
const LIVE_STATES = new Set(['near', 'armed', 'pullback', 'leg']);

export function pillarLetter(name: string): string {
  return WATCHLIST_PILLAR_LETTERS[name] ?? name.slice(0, 1).toUpperCase();
}

export type Tone = '' | 'good' | 'warn' | 'bad' | 'muted';

export interface Cell {
  text: string;
  title: string;
  tone: Tone;
}

/** The News cell: today's catalyst verdict, else the scanner's article flag, stated as such. */
export function newsCell(entry: WatchlistEntry): Cell {
  const c = entry.catalyst;
  if (!c) {
    if (entry.has_news) {
      return { text: 'Article', title: 'An article exists; no catalyst source has been read for it yet.', tone: 'muted' };
    }
    return { text: '—', title: 'Catalyst not read yet (unknown, not "no news").', tone: 'muted' };
  }
  const when = c.published_ts ? ` · ${fmtEtClock(c.published_ts)} ET` : '';
  const head = c.title ? `\n${c.title}` : '';
  if (c.news_pending) {
    return { text: 'Pending', title: 'Halted for news (T1 / T12) with no resumption yet: the news is coming.', tone: 'warn' };
  }
  if (c.verdict === 'catalyst' || c.verdict === 'negative') {
    const cat = c.category ?? '';
    const full = CATALYST_CATEGORY_LABELS[cat] ?? cat;
    const strength = c.strength ? ` (${c.strength})` : '';
    return {
      text: CATALYST_CATEGORY_SHORT[cat] ?? (full || 'Catalyst'),
      title: `${CATALYST_VERDICT_TITLES[c.verdict] ?? c.verdict}: ${full}${strength}${when}${head}`,
      tone: c.verdict === 'negative' ? 'bad' : 'good',
    };
  }
  const label: Record<string, string> = { routine_only: 'Routine', noise_only: 'Noise', none_found: 'None' };
  return {
    text: label[c.verdict] ?? '—',
    title: `${CATALYST_VERDICT_TITLES[c.verdict] ?? c.verdict}${when}${head}`,
    tone: 'muted',
  };
}

/** The News column's sort rank, the order the cell reads in (higher first):
 * a strong catalyst, a weak one, halted for news, bad news, routine, noise,
 * then nothing found. Not read yet -- an article flag or no verdict -- is
 * null and sorts last. */
export function newsSortRank(entry: WatchlistEntry): number | null {
  const c = entry.catalyst;
  if (!c) return null;
  if (c.news_pending) return 4;
  if (c.verdict === 'catalyst') return c.strength === 'strong' ? 6 : 5;
  if (c.verdict === 'negative') return 3;
  const rank: Record<string, number> = { routine_only: 2, noise_only: 1, none_found: 0 };
  return rank[c.verdict] ?? null;
}

function fmtEtClock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

function fmtLevel(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

/** The Setup cell: the symbol's most advanced setup on the board (ADR 031), named, with its hover. */
export function setupCell(row: SetupRow | undefined, following: boolean): Cell {
  if (!row) {
    return {
      text: '—',
      title: following
        ? 'Not on the setup board (it lists the setups in play).'
        : 'Setup scanner not connected.',
      tone: 'muted',
    };
  }
  const words = stateWords(row);
  const name = setupShort(setupTypeOf(row));
  const title = `${words.title}\n${words.tip}`;
  if (row.state === 'near' || row.state === 'armed') {
    const trigger = fmtLevel(row.setup?.trigger);
    const text = `${name} · ${words.text}${trigger ? ` · ${trigger}` : ''}`;
    return { text, title, tone: row.state === 'near' ? 'good' : '' };
  }
  if (row.state === 'failed') return { text: `${name} · ${words.text}`, title, tone: 'bad' };
  if (row.state === 'watching') return { text: '—', title, tone: 'muted' };
  return { text: `${name} · ${words.text}`, title, tone: row.state === 'triggered' ? 'good' : 'muted' };
}

export function isSetupLive(row: SetupRow | undefined): boolean {
  return row != null && LIVE_STATES.has(row.state);
}

export function applyFilter(
  entries: WatchlistEntry[],
  filter: WatchlistFilter,
  setups: Map<string, SetupRow>,
  isAllowed: (symbol: string) => boolean,
): WatchlistEntry[] {
  if (filter === 'pillars5') return entries.filter(e => e.five_pillars.all_pass);
  if (filter === 'setup_live') return entries.filter(e => isSetupLive(setups.get(e.symbol)));
  if (filter === 'allowlist') return entries.filter(e => isAllowed(e.symbol));
  return entries;
}

export interface WatchlistSummary {
  total: number;
  allPass: number;
  setupsLive: number;
  near: number;
  allowlisted: number;
}

export function summarize(
  entries: WatchlistEntry[],
  setups: Map<string, SetupRow>,
  isAllowed: (symbol: string) => boolean,
): WatchlistSummary {
  let allPass = 0;
  let setupsLive = 0;
  let near = 0;
  let allowlisted = 0;
  for (const e of entries) {
    if (e.five_pillars.all_pass) allPass += 1;
    const row = setups.get(e.symbol);
    if (isSetupLive(row)) setupsLive += 1;
    if (row?.state === 'near') near += 1;
    if (isAllowed(e.symbol)) allowlisted += 1;
  }
  return { total: entries.length, allPass, setupsLive, near, allowlisted };
}

/** Board rows by symbol; a symbol on several setups (ADR 031) shows its most advanced one. */
export function setupsBySymbol(rows: SetupRow[] | null | undefined): Map<string, SetupRow> {
  const out = new Map<string, SetupRow>();
  for (const r of rows ?? []) {
    const had = out.get(r.symbol);
    if (!had || rowRank(r) < rowRank(had)) out.set(r.symbol, r);
  }
  return out;
}
