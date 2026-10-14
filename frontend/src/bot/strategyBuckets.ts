/** Strategy buckets follow the operator's switch. Research results describe evidence, never permission. */
import {
  BOT_READOUT_STATE_LABELS,
  BOT_READOUT_WHAT,
  BOT_WATCH_ONLY_LEVEL_TIP,
  BOT_WATCH_ONLY_STATUS,
  isWatchOnlySetup,
} from '../constantGroups/bot';
import {
  BOTS_BUCKET_LOADING_READOUT,
  BOTS_BUCKET_LOADING_READOUT_TIP,
  BOTS_BUCKET_NO_READOUT,
  BOTS_BUCKET_NO_READOUT_TIP,
  BOTS_BUCKET_NO_TEST,
  BOTS_BUCKET_NO_TEST_TIP,
} from '../constantGroups/bots_page';
import { SHORT_TEST_STALE_TIP, SHORT_TEST_STATE_WORDS } from '../constantGroups/short_setups';
import type { ShortTest } from '../setups';
import type { TemplateReadout } from './templateTypes';

export type Bucket = 0 | 1 | 2;

export interface BucketRow {
  id: string;
  label: string;
  side: 'long' | 'short';
  /** The strategy's own switch: 0 Off, 1 Eyes, 2 On. */
  own: Bucket;
  /** Legacy lock field; research never changes the chosen bucket. */
  locked: string | null;
  test: ShortTest | null;
  /** The template in play's read-out: undefined while the templates load, null when the backend reports none. */
  readout: TemplateReadout | null | undefined;
}

export type StatusTone = 'ok' | 'bad' | 'held' | 'muted';

export interface BucketStatus {
  text: string;
  tone: StatusTone;
  tip: string;
}

/** The bucket a strategy sits in is its own level, independent of research results. */
export function bucketOf(row: BucketRow): Bucket {
  return row.own;
}

function testStatus(row: BucketRow): BucketStatus {
  const test = row.test;
  if (!test) return { text: BOTS_BUCKET_NO_TEST, tone: 'muted', tip: BOTS_BUCKET_NO_TEST_TIP };
  const state = SHORT_TEST_STATE_WORDS[test.state] ? test.state : 'error';
  const tone: StatusTone = state === 'passed' && test.matches !== false ? 'ok'
    : state === 'failed' || state === 'error' ? 'bad' : 'muted';
  const tip = [test.text, test.matches === false ? SHORT_TEST_STALE_TIP : ''].filter(Boolean).join('\n');
  return { text: `Test ${SHORT_TEST_STATE_WORDS[state]}`, tone, tip };
}

function readoutStatus(readout: TemplateReadout | null | undefined): BucketStatus {
  if (readout === undefined) return { text: BOTS_BUCKET_LOADING_READOUT, tone: 'muted', tip: BOTS_BUCKET_LOADING_READOUT_TIP };
  if (!readout) return { text: BOTS_BUCKET_NO_READOUT, tone: 'muted', tip: BOTS_BUCKET_NO_READOUT_TIP };
  const state = (BOT_READOUT_STATE_LABELS[readout.state] ?? readout.state).toLowerCase();
  const go = readout.go_triggered ?? 0;
  const min = readout.min_go ?? 50;
  const tone: StatusTone = readout.state === 'passed' ? 'ok' : readout.state === 'failed' ? 'bad' : 'muted';
  return {
    text: `Read-out ${state} · ${go}/${min} go`,
    tone,
    tip: [readout.reason ?? '', BOT_READOUT_WHAT].filter(Boolean).join('\n'),
  };
}

/** How far a strategy's evidence has come: a short's five-year test, a long's read-out; a watch-only one (#847)
 * says it first. */
export function statusOf(row: BucketRow): BucketStatus {
  if (isWatchOnlySetup(row.id)) {
    const r = readoutStatus(row.readout);
    return { text: `${BOT_WATCH_ONLY_STATUS} · ${r.text.toLowerCase()}`, tone: r.tone,
      tip: [BOT_WATCH_ONLY_LEVEL_TIP, r.tip].filter(Boolean).join('\n') };
  }
  if (row.side === 'short') {
    return testStatus(row);
  }
  return readoutStatus(row.readout);
}

/** The rows of each bucket, in the order given (the playbook's). */
export function bucketsOf(rows: readonly BucketRow[]): Record<Bucket, BucketRow[]> {
  const out: Record<Bucket, BucketRow[]> = { 2: [], 1: [], 0: [] };
  for (const row of rows) out[bucketOf(row)].push(row);
  return out;
}
