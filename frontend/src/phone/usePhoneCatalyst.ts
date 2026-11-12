/**
 * One stock's Catalyst call for a phone row: the desk's shared read (`useCatalystRead`, one request a
 * board) and the desk's own face for it, put into the phone's two short lines. On an API from before
 * the batch read the cell is never "reading": it falls back to the row's own news verdict.
 */
import { useCatalystRead } from '../hooks/useCatalystRead';
import type { CatalystVerdict } from '../types/catalystVerdict';
import { catalystFace } from '../utils/catalystCause';
import { phoneCatalyst, type PhoneCatalyst } from './phoneCatalyst';

export function usePhoneCatalyst(symbol: string, board: string | null, row: {
  /** The row's own verdict, when the screen has one (a scanner row). */
  verdict?: CatalystVerdict | null;
  halted: boolean;
  resumeTs?: number | null;
  nowMs: number;
}): PhoneCatalyst {
  const read = useCatalystRead(symbol, board);
  const verdict = read.read?.facts?.catalyst ?? row.verdict ?? null;
  const face = catalystFace(read.read, verdict, row.nowMs, read.loading && !read.unavailable);
  return phoneCatalyst({ face, verdict, halted: row.halted, resumeTs: row.resumeTs ?? null, nowMs: row.nowMs });
}
