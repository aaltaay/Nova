/**
 * How a Session Record row reads, shared by the Records page, the Sim Day /
 * Ticker pickers and the Sim tab's own-recording line so they cannot disagree
 * (QA 2026-09-22, C21 / C22 / C64). Words, never the manifest's raw codes; an
 * uncounted recording says it has prints, never "-1".
 */
import {
  CAPTURE_EMPTY_REASON,
  CAPTURE_NOT_IBKR_REASON,
  CAPTURE_PRINTS_PRESENT,
  CAPTURE_PRINTS_PRESENT_SHORT,
  CAPTURE_PRINTS_RECORDING,
  CAPTURE_REASON_WORDS,
  CAPTURE_SOURCE_IBKR,
  CAPTURE_STATUS_WORDS,
} from './simConstants';
import type { CaptureSessionRow } from './useSimSessionController';

const counted = (prints: number | null | undefined): prints is number =>
  prints != null && Number.isFinite(prints) && prints >= 0;

/** A replayable real recording: IBKR-sourced (or an older listing without a source), not empty, usable. */
export function recordingUsable(row: CaptureSessionRow): boolean {
  if (row.usable === false || row.empty) return false;
  return row.source == null || row.source === CAPTURE_SOURCE_IBKR;
}

/** Why a row cannot be replayed; null when it can. */
export function recordingUnavailableReason(row: CaptureSessionRow): string | null {
  if (recordingUsable(row)) return null;
  if (row.unavailable_reason) return row.unavailable_reason;
  if (row.source != null && row.source !== CAPTURE_SOURCE_IBKR) return CAPTURE_NOT_IBKR_REASON;
  return CAPTURE_EMPTY_REASON;
}

/** "1,234 prints", or "prints present" when Nova has not counted them yet. */
export function recordPrintsLabel(prints: number | null | undefined): string {
  return counted(prints) ? `${prints.toLocaleString()} prints` : CAPTURE_PRINTS_PRESENT;
}

/** "1234p" / "data present", for a picker option. */
export function recordPrintsShort(prints: number | null | undefined): string {
  return counted(prints) ? `${prints}p` : CAPTURE_PRINTS_PRESENT_SHORT;
}

/** The Records cell: the count, or what Nova knows instead of a number. */
export function recordPrintsCell(prints: number | null | undefined, recording: boolean): string {
  if (counted(prints)) return prints.toLocaleString();
  return recording ? CAPTURE_PRINTS_RECORDING : CAPTURE_PRINTS_PRESENT;
}

/** The manifest status in words; the last segment's reason when there is no status. */
export function recordStatusWords(row: CaptureSessionRow): string | null {
  if (row.status) return CAPTURE_STATUS_WORDS[row.status] ?? row.status.replace(/_/g, ' ');
  if (row.last_reason) return CAPTURE_REASON_WORDS[row.last_reason] ?? row.last_reason;
  return null;
}
