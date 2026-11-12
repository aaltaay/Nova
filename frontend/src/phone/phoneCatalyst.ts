/**
 * What is moving a stock, in the two short lines a phone row has room for. The call is the desk's
 * own (`catalystFace`, ADR 028): this file only picks which of its words fit -- the desk's word on
 * top, and under it how old the news is, where the desk's cell has room for the headline. Pure.
 */
import { CATALYST_SOURCE_LABELS } from '../constants';
import type { CatalystVerdict } from '../types/catalystVerdict';
import type { CatalystFace } from '../utils/catalystCause';
import { agoShort } from './phoneFormat';

export type CatalystTone = 'news' | 'bad' | 'plain';

export interface PhoneCatalyst {
  word: string;
  /** The second line: an age, a halt's return, or the desk's own detail. May be empty. */
  when: string;
  tone: CatalystTone;
  /** The headline behind a news word, for the stock page's strip; null when there is none. */
  headline: string | null;
  url: string | null;
}

const NEWS_MARKS = new Set(['flame', 'ring', 'routine']);

function headlineOf(verdict: CatalystVerdict | null | undefined): string | null {
  const title = verdict?.title?.trim();
  if (!title) return null;
  // An EDGAR title reads "<form: items> | <release headline>": the headline is the part a person reads.
  return verdict?.source === 'edgar' && title.includes(' | ') ? title.split(' | ').slice(1).join(' | ').trim() : title;
}

export interface CatalystInput {
  face: CatalystFace;
  verdict: CatalystVerdict | null | undefined;
  halted: boolean;
  /** When trading is listed to resume, epoch seconds; null when the exchange has listed none. */
  resumeTs?: number | null;
  nowMs: number;
}

const HHMM_ET = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
});

export function phoneCatalyst({ face, verdict, halted, resumeTs = null, nowMs }: CatalystInput): PhoneCatalyst {
  const headline = headlineOf(verdict);
  const url = verdict?.url ?? null;
  if (halted) {
    const back = resumeTs != null && Number.isFinite(resumeTs) ? `back ${HHMM_ET.format(new Date(resumeTs * 1000))}` : '';
    return { word: 'Halted', when: back, tone: 'bad', headline, url };
  }
  const published = verdict?.published_ts != null ? agoShort(nowMs - verdict.published_ts * 1000) : '';
  if (face.mark === 'negative') return { word: face.word || 'News', when: published || face.detail || '', tone: 'bad', headline, url };
  if (NEWS_MARKS.has(face.mark)) return { word: face.word || 'News', when: published || face.detail || '', tone: 'news', headline, url };
  if (face.mark === 'pending') return { word: face.word, when: face.detail ?? '', tone: 'bad', headline, url };
  if (face.mark === 'reading') return { word: 'Reading', when: '', tone: 'plain', headline: null, url: null };
  if (face.word) return { word: face.word, when: face.detail ?? '', tone: 'plain', headline, url };
  // No cause named. Only a verdict that looked and found nothing may say so.
  if (verdict?.verdict === 'none_found') return { word: 'No news', when: 'found', tone: 'plain', headline: null, url: null };
  return { word: '—', when: '', tone: 'plain', headline: null, url: null };
}

/** The same two lines on one: "News · 9m ago". */
export function catalystLine(c: PhoneCatalyst): string {
  return c.when ? `${c.word} · ${c.when}` : c.word;
}

/** Where a headline came from, as the desk names it: "SEC", "GlobeNewswire". */
export function sourceWord(verdict: CatalystVerdict | null | undefined): string | null {
  const source = verdict?.source;
  if (!source) return null;
  return (CATALYST_SOURCE_LABELS as Record<string, string | undefined>)[source] ?? source;
}
