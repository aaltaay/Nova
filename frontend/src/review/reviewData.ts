/** Load one review page, then cut again so a late bar cannot be painted. */

import type { ReviewPayload } from './reviewFixture';
import { cutBars, dailyAtCutoff } from './reviewCut';
import { loopbackApi, type ReviewTf } from './reviewQuery';

/** The page's own code when the answer names none (a reader failure, a bad schema, no connection). */
export const REVIEW_PAGE_ERROR = 'REVIEW_PAGE_ERROR';

/** Why a review day could not be loaded: the route's code (`REVIEW_NO_DATA`) and its words. */
export class ReviewLoadError extends Error {
  readonly code: string;

  constructor(message: string, code = REVIEW_PAGE_ERROR) {
    super(message);
    this.name = 'ReviewLoadError';
    this.code = code;
  }
}

export function reviewLoadError(reason: unknown): ReviewLoadError {
  if (reason instanceof ReviewLoadError) return reason;
  return new ReviewLoadError(reason instanceof Error ? reason.message : String(reason));
}

export async function fetchReview(
  symbol: string, date: string, tfs: ReviewTf[], asOf: string, api = '',
): Promise<ReviewPayload> {
  const params = new URLSearchParams({ symbol, date, tf: tfs.join(','), as_of: asOf });
  const base = loopbackApi(api);
  const response = await fetch(`${base}/api/review?${params.toString()}`);
  const body = await response.json().catch(() => null) as
    { ok?: boolean; error?: unknown; code?: unknown; schema_version?: number } | null;
  if (!response.ok || !body?.ok) {
    const detail = body?.error ?? `HTTP ${response.status}`;
    throw new ReviewLoadError(
      typeof detail === 'string' ? detail : JSON.stringify(detail),
      typeof body?.code === 'string' ? body.code : REVIEW_PAGE_ERROR,
    );
  }
  if (body.schema_version !== 1) throw new ReviewLoadError(`review schema ${body.schema_version}`);
  return body as ReviewPayload;
}

export function cutPayload(payload: ReviewPayload): ReviewPayload {
  const timeframes = { ...payload.timeframes };
  for (const tf of Object.keys(timeframes) as ReviewTf[]) {
    const frame = timeframes[tf];
    if (!frame) continue;
    timeframes[tf] = { ...frame, bars: cutBars(frame.bars, tf, payload.as_of_iso) };
  }
  if (timeframes['1d']) {
    timeframes['1d'] = {
      ...timeframes['1d'],
      bars: dailyAtCutoff(payload.date, timeframes['1d'].bars, timeframes['1m']?.bars ?? [], payload.as_of_iso),
    };
  }
  return { ...payload, timeframes };
}
