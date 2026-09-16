import {
  NEWS_FLAME_HOT_HOURS,
  NEWS_FLAME_MAX_HOURS,
  NEWS_FLAME_WARM_HOURS,
} from '../constantGroups/market_ui';
import {
  NEWS_JUNK_HEADLINE_PHRASES,
  NEWS_JUNK_HEADLINE_RES,
  NEWS_JUNK_SECTOR_ROUNDUP_RE,
  NEWS_JUNK_URL_FRAGMENTS,
  NEWS_SIGNAL_HEADLINE_KEYWORDS,
} from '../constantGroups/news_junk';

const HEADLINE_RES = NEWS_JUNK_HEADLINE_RES.map((pat) => new RegExp(pat, 'i'));
const SECTOR_RE = new RegExp(NEWS_JUNK_SECTOR_ROUNDUP_RE, 'i');

export type NewsChipFlame = 'flame-hot' | 'flame-warm' | 'flame-cool';

export interface NewsJunkInput {
  headline?: string;
  url?: string;
  created_at: string;
}

function hasSignal(text: string): boolean {
  return NEWS_SIGNAL_HEADLINE_KEYWORDS.some((key) => text.includes(key));
}

export function isJunkHeadline(headline: string, url = ''): boolean {
  const text = (headline || '').trim().toLowerCase();
  const urlL = (url || '').trim().toLowerCase();
  if (NEWS_JUNK_URL_FRAGMENTS.some((frag) => urlL.includes(frag))) return true;
  if (!text) return false;
  if (HEADLINE_RES.some((rx) => rx.test(text))) return true;
  if (NEWS_JUNK_HEADLINE_PHRASES.some((phrase) => text.includes(phrase))) return true;
  if (SECTOR_RE.test(text) && !hasSignal(text)) return true;
  return false;
}

export function filterSignalNews<T extends { headline?: string; url?: string }>(
  news: T[],
): T[] {
  return news.filter((row) => !isJunkHeadline(row.headline ?? '', row.url ?? ''));
}

export function newsChipFlameClass(
  article: NewsJunkInput,
  nowMs: number = Date.now(),
): NewsChipFlame | null {
  if (isJunkHeadline(article.headline ?? '', article.url ?? '')) return null;
  const ageHours = (nowMs - new Date(article.created_at).getTime()) / 3_600_000;
  if (!Number.isFinite(ageHours) || ageHours > NEWS_FLAME_MAX_HOURS) return null;
  if (ageHours <= NEWS_FLAME_HOT_HOURS) return 'flame-hot';
  if (ageHours <= NEWS_FLAME_WARM_HOURS) return 'flame-warm';
  return 'flame-cool';
}
