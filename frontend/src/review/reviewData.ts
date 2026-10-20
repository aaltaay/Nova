/** Load one review page, then cut again so a late bar cannot be painted. */

import type { ReviewPayload } from './reviewFixture';
import { cutBars, dailyAtCutoff } from './reviewCut';
import { loopbackApi, type ReviewTf } from './reviewQuery';

export async function fetchReview(
  symbol: string, date: string, tfs: ReviewTf[], asOf: string, api = '',
): Promise<ReviewPayload> {
  const params = new URLSearchParams({ symbol, date, tf: tfs.join(','), as_of: asOf });
  const base = loopbackApi(api);
  const response = await fetch(`${base}/api/review?${params.toString()}`);
  const body = await response.json().catch(() => null) as { ok?: boolean; error?: unknown; schema_version?: number } | null;
  if (!response.ok || !body?.ok) {
    const detail = body?.error ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  if (body.schema_version !== 1) throw new Error(`review schema ${body.schema_version}`);
  return body as ReviewPayload;
}

export function cutPayload(payload: ReviewPayload): ReviewPayload {
  const timeframes = { ...payload.timeframes };
  for (const tf of Object.keys(timeframes) as ReviewTf[]) {
    const frame = timeframes[tf];
    if (!frame) continue;
    timeframes[tf] = { bars: cutBars(frame.bars, tf, payload.as_of_iso) };
  }
  if (timeframes['1d']) {
    timeframes['1d'] = {
      bars: dailyAtCutoff(payload.date, timeframes['1d'].bars, timeframes['1m']?.bars ?? [], payload.as_of_iso),
    };
  }
  return { ...payload, timeframes };
}
