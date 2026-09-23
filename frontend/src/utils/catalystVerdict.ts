/**
 * Reading a catalyst verdict (ADR 024) on the desk: the wire shape, the News column's mark and the
 * words behind it. Pure; unknown stays unknown -- a verdict nobody read is never "no news".
 */
import {
  CATALYST_CATEGORY_LABELS,
  CATALYST_NEWS_ALSO_NEGATIVE,
  CATALYST_NEWS_CHECKED_PREFIX,
  CATALYST_NEWS_PENDING_TITLE,
  CATALYST_NEWS_UNPLACED_NOTE,
  CATALYST_NEWS_UNREAD_TITLE,
  CATALYST_PRIMARY_SOURCES,
  CATALYST_SOURCE_LABELS,
  CATALYST_VERDICT_TITLES,
} from '../constantGroups/catalysts';
import { NEWS_FLAME_HOT_HOURS, NEWS_FLAME_WARM_HOURS } from '../constantGroups/market_ui';
import type { CatalystVerdict, CatalystVerdictKind } from '../types/catalystVerdict';

const VERDICTS: ReadonlySet<string> = new Set<CatalystVerdictKind>([
  'catalyst', 'negative', 'routine_only', 'noise_only', 'none_found', 'not_checked',
]);
const UNPLACED = 'company_news';

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** A verdict off the wire, or null when it is absent or not one. */
export function normalizeCatalystVerdict(raw: unknown): CatalystVerdict | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.verdict !== 'string' || !VERDICTS.has(r.verdict)) return null;
  return {
    verdict: r.verdict as CatalystVerdictKind,
    category: text(r.category),
    strength: r.strength === 'strong' || r.strength === 'weak' ? r.strength : null,
    title: text(r.title),
    source: text(r.source),
    published_ts: finite(r.published_ts),
    url: text(r.url),
    negative_too: r.negative_too === true,
    rules_version: text(r.rules_version) ?? '',
    sources_answered: Array.isArray(r.sources_answered)
      ? r.sources_answered.filter((s): s is string => typeof s === 'string')
      : undefined,
    n_items: finite(r.n_items) ?? undefined,
    news_pending: r.news_pending === true,
    halt_code: text(r.halt_code),
  };
}

/** True when a source actually read this symbol (a verdict other than "not checked"). */
export function isVerdictRead(v: CatalystVerdict | null | undefined): v is CatalystVerdict {
  return !!v && v.verdict !== 'not_checked';
}

/** News the trader must see: a catalyst, dilution / a reverse split, or a halt for pending news. */
export function isCompanyNews(v: CatalystVerdict | null | undefined): boolean {
  return !!v && (v.verdict === 'catalyst' || v.verdict === 'negative' || v.news_pending === true);
}

/** An EDGAR title without its "<form: items> | " prefix; anything else as it came. */
export function catalystHeadline(title: string | null | undefined, source: string | null | undefined): string {
  const t = (title ?? '').trim();
  if (source === 'edgar' && t.includes(' | ')) return t.slice(t.indexOf(' | ') + 3).trim();
  return t;
}

export function sourceLabel(source: string | null | undefined): string {
  if (!source) return '';
  return CATALYST_SOURCE_LABELS[source] ?? source;
}

export function isPrimarySource(source: string | null | undefined): boolean {
  return !!source && CATALYST_PRIMARY_SOURCES.includes(source);
}

export function categoryLabel(category: string | null | undefined): string {
  if (!category) return '';
  return CATALYST_CATEGORY_LABELS[category] ?? category.replace(/_/g, ' ');
}

/** "38m ago" / "5h ago" from epoch seconds. */
export function agoLabel(ts: number | null | undefined, nowMs: number): string {
  if (ts == null) return '';
  const minutes = Math.max(0, (nowMs - ts * 1000) / 60_000);
  return minutes < 60 ? `${Math.round(minutes)}m ago` : `${Math.floor(minutes / 60)}h ago`;
}

export type NewsMarkKind = 'flame' | 'ring' | 'negative' | 'pending' | 'routine' | 'none';

export interface NewsMark {
  kind: NewsMarkKind;
  /** flame-hot | flame-warm | flame-cool by the item's age (flame and ring only). */
  ageClass: string | null;
  title: string;
}

function ageClass(ts: number | null, nowMs: number): string {
  if (ts == null) return 'flame-cool';
  const hours = (nowMs - ts * 1000) / 3_600_000;
  if (hours <= NEWS_FLAME_HOT_HOURS) return 'flame-hot';
  if (hours <= NEWS_FLAME_WARM_HOURS) return 'flame-warm';
  return 'flame-cool';
}

/** The words behind a verdict: what it is, the headline, where from, how old, what was checked. */
export function verdictTooltip(v: CatalystVerdict | null | undefined, nowMs: number): string {
  if (!v) return CATALYST_NEWS_UNREAD_TITLE;
  const lines: string[] = [];
  if (v.news_pending) lines.push(`${CATALYST_NEWS_PENDING_TITLE}${v.halt_code ? ` (${v.halt_code})` : ''}`);
  const head = CATALYST_VERDICT_TITLES[v.verdict] ?? v.verdict;
  if (v.verdict === 'catalyst' || v.verdict === 'negative') {
    const strength = v.strength ? ` (${v.strength})` : '';
    lines.push(`${head}: ${categoryLabel(v.category)}${strength}`);
    const headline = catalystHeadline(v.title, v.source);
    if (headline) lines.push(headline);
    const meta = [sourceLabel(v.source), agoLabel(v.published_ts, nowMs)].filter(Boolean).join(' · ');
    if (meta) lines.push(meta);
    if (v.verdict === 'catalyst' && v.category === UNPLACED) lines.push(CATALYST_NEWS_UNPLACED_NOTE);
    if (v.verdict === 'catalyst' && v.negative_too) lines.push(CATALYST_NEWS_ALSO_NEGATIVE);
  } else {
    lines.push(head);
  }
  if (v.sources_answered?.length) {
    lines.push(`${CATALYST_NEWS_CHECKED_PREFIX}: ${v.sources_answered.map(sourceLabel).join(', ')}`);
  }
  return lines.join('\n');
}

/** The News column's mark for a row that carries a verdict (`undefined` rows keep the headline flame). */
export function newsMark(v: CatalystVerdict | null, nowMs: number): NewsMark {
  const title = verdictTooltip(v, nowMs);
  if (!v) return { kind: 'none', ageClass: null, title };
  if (v.news_pending) return { kind: 'pending', ageClass: null, title };
  switch (v.verdict) {
    case 'catalyst':
      return { kind: v.category === UNPLACED ? 'ring' : 'flame', ageClass: ageClass(v.published_ts, nowMs), title };
    case 'negative':
      return { kind: 'negative', ageClass: null, title };
    case 'routine_only':
      return { kind: 'routine', ageClass: null, title };
    default:
      return { kind: 'none', ageClass: null, title };
  }
}
