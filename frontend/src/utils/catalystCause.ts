/**
 * The Catalyst cell's face (ADR 028 amendment 2026-10-12): the read's likely cause as a mark, a word and a short
 * second line. News keeps the News column's marks (a flame by age, the ring, `!`, `H`, the routine dot) and the
 * catalyst class's word; a move with no news gets its cause's mark. Every word comes from the read's own checks
 * -- nothing is filled in: an unknown fact makes the cause `possible` (hollow mark, "?"), never a guess. Pure.
 */
import {
  CATALYST_CATEGORY_SHORT,
  CATALYST_CAUSE_WORDS,
  CATALYST_DETAIL_BORROW_TIGHT,
  CATALYST_DETAIL_NEWS_UNREAD,
  CATALYST_DETAIL_NO_NEWS,
  CATALYST_DETAIL_NOTHING_TO_LEND,
  CATALYST_DETAIL_UNEXPLAINED,
  CATALYST_NEWS_WORD,
  CATALYST_UNPLACED_CATEGORY,
  CATALYST_UNPLACED_WORD,
} from '../constants';
import type { CatalystVerdict } from '../types/catalystVerdict';
import type { WhyCheck, WhyMovingRead } from '../types/whyMoving';
import { newsMark } from './catalystVerdict';

export type CatalystMarkKind =
  | 'flame' | 'ring' | 'negative' | 'pending' | 'routine'
  | 'squeeze' | 'split' | 'lowfloat' | 'thin' | 'unexplained'
  | 'none' | 'reading';

export interface CatalystFace {
  mark: CatalystMarkKind;
  /** flame-hot | flame-warm | flame-cool for a news flame or ring. */
  ageClass: string | null;
  word: string;
  detail: string | null;
  /** A deciding fact is unknown: hollow mark, the word with "?". */
  possible: boolean;
  /** News, and the short-squeeze checks pass too. */
  squeezePip: boolean;
  /** The cause's kind, for tests and `data-` attributes. */
  kind: string;
}

const NONE: Omit<CatalystFace, 'kind'> = { mark: 'none', ageClass: null, word: '', detail: null, possible: false, squeezePip: false };

function check(read: WhyMovingRead, id: string): WhyCheck | null {
  return read.checks.find(c => c.id === id) ?? null;
}

function lc(text: string): string {
  return text.slice(0, 1).toLowerCase() + text.slice(1);
}

/** "Fee 151.6%/yr · 15K shares to lend" -> "fee 151.6%/yr"; "Nothing to lend" -> "nothing to lend". */
function borrowWords(c: WhyCheck | null): string | null {
  if (!c || c.state !== 'yes' || !c.value) return null;
  return c.value === 'Nothing to lend' ? CATALYST_DETAIL_NOTHING_TO_LEND : lc(c.value.split(' · ')[0]);
}

function headline(v: CatalystVerdict | null): string | null {
  const title = v?.title?.trim();
  if (!title) return null;
  return v?.source === 'edgar' && title.includes(' | ') ? title.split(' | ').slice(1).join(' | ').trim() : title;
}

/** News as the News column marked it: a flame by age, the ring for unplaced news, `!` for bad news. */
function newsFace(verdict: CatalystVerdict | null, nowMs: number, squeezePip: boolean): Omit<CatalystFace, 'kind'> {
  const mark = newsMark(verdict, nowMs);
  const face: CatalystMarkKind = mark.kind === 'negative' ? 'negative' : mark.kind === 'ring' ? 'ring' : 'flame';
  const category = verdict?.category === CATALYST_UNPLACED_CATEGORY ? CATALYST_UNPLACED_WORD
    : verdict?.category ? CATALYST_CATEGORY_SHORT[verdict.category] ?? verdict.category : null;
  const strength = verdict?.strength ? `${verdict.strength} · ` : '';
  return {
    ...NONE,
    mark: face,
    ageClass: mark.ageClass,
    word: category ?? CATALYST_NEWS_WORD,
    detail: `${strength}${headline(verdict) ?? ''}`.replace(/ · $/, '') || null,
    squeezePip,
  };
}

export function catalystFace(read: WhyMovingRead | null, rowVerdict: CatalystVerdict | null | undefined,
  nowMs: number, loading = false): CatalystFace {
  if (!read) return { ...NONE, mark: loading ? 'reading' : 'none', kind: loading ? 'reading' : 'none' };
  const { kind, confidence } = read.likely;
  const possible = confidence === 'possible';
  const verdict = read.facts?.catalyst ?? rowVerdict ?? null;
  const steps = read.likely.steps ?? [];
  const word = (w: string) => (possible ? `${w}?` : w);
  // No price on record (a Losers row IBKR never quoted): no cause is claimed -- the news mark if there is news.
  if (steps[0]?.kind === 'move' && steps[0].fits === null) {
    if (verdict?.news_pending) return { ...NONE, kind: 'news_pending', mark: 'pending', word: CATALYST_CAUSE_WORDS.news_pending };
    if (verdict?.verdict === 'catalyst' || verdict?.verdict === 'negative') return { ...newsFace(verdict, nowMs, false), kind: 'news' };
    return { ...NONE, kind: 'no_price' };
  }
  switch (kind) {
    case 'news_pending':
      return { ...NONE, kind, mark: 'pending', word: CATALYST_CAUSE_WORDS.news_pending, detail: verdict?.halt_code ?? null };
    case 'news':
      return { ...newsFace(verdict, nowMs, steps.some(s => s.kind === 'short_squeeze' && s.fits === true)), kind };
    case 'routine_news':
      return { ...NONE, kind, mark: 'routine', word: CATALYST_CAUSE_WORDS.routine_news, detail: headline(verdict) };
    case 'short_squeeze': {
      const short = check(read, 'short_interest')?.value?.split(' · ')[0] ?? null;
      const parts = [short ? `${short} short` : null, borrowWords(check(read, 'borrow'))].filter(Boolean);
      return { ...NONE, kind, mark: 'squeeze', possible, word: word(CATALYST_CAUSE_WORDS.short_squeeze), detail: parts.join(' · ') || null };
    }
    case 'split_squeeze':
      return { ...NONE, kind, mark: 'split', possible, word: word(CATALYST_CAUSE_WORDS.split_squeeze),
        detail: check(read, 'reverse_split')?.value ?? null };
    case 'low_float_momentum': {
      const borrow = check(read, 'borrow');
      const lend = borrow?.state === 'yes'
        ? (borrow.value === 'Nothing to lend' ? CATALYST_DETAIL_NOTHING_TO_LEND : CATALYST_DETAIL_BORROW_TIGHT) : null;
      const news = possible ? CATALYST_DETAIL_NEWS_UNREAD : CATALYST_DETAIL_NO_NEWS;
      return { ...NONE, kind, mark: 'lowfloat', possible, word: word(CATALYST_CAUSE_WORDS.low_float_momentum),
        detail: [news, lend].filter(Boolean).join(' · ') };
    }
    case 'thin_trading':
      return { ...NONE, kind, mark: 'thin', possible, word: word(CATALYST_CAUSE_WORDS.thin_trading),
        detail: check(read, 'volume')?.value ?? null };
    case 'unexplained':
      return { ...NONE, kind, mark: 'unexplained', possible, word: word(CATALYST_CAUSE_WORDS.unexplained),
        detail: CATALYST_DETAIL_UNEXPLAINED };
    default:  // not_moving, not_read: a dash, and the hover says why
      return { ...NONE, kind };
  }
}
