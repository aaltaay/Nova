/** Load one review page, then cut again so a late bar cannot be painted. */

import type { ReviewPayload } from './reviewFixture';
import { cutBars } from './reviewCut';
import type { ReviewTf } from './reviewQuery';

export async function fetchReview(symbol: string, date: string, tfs: ReviewTf[], asOf: string): Promise<ReviewPayload> {
  const params = new URLSearchParams({ symbol, date, tf: tfs.join(','), as_of: asOf });
  const response = await fetch(`/api/review?${params.toString()}`);
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
  return { ...payload, timeframes };
}
