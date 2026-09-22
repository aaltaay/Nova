/**
 * What a mirrored scanner list says when it has no rows (QA D10, 2026-09-22):
 * the Desk board and the Focus rail said "Gappers: no rows right now" while
 * the first request was still pending and while every route was failing. A
 * failure is named, a pending load says so, and only a loaded, empty list is
 * "no rows right now". Pure.
 */
import { listFeedFailed, listFeedLoading } from '../constantGroups/scanner_board';

export interface ListFeedState {
  /** A scanner REST route failed (text names it), or null. */
  restError?: string | null;
  /** `health.status` -- 'loading' until the first scan answers. */
  healthStatus?: string | null;
}

export function listAbsenceText(title: string, feed: ListFeedState, empty: (title: string) => string): string {
  if (feed.restError) return listFeedFailed(title, feed.restError);
  if (feed.healthStatus === 'loading') return listFeedLoading(title);
  return empty(title);
}
