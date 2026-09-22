/**
 * The Level 2 header chip while a Session Record replays (QA 2026-09-22, R16).
 * Today's halt and shortability chips describe today, not the replayed
 * session, so a capture replay shows what the recording holds instead: its
 * Level 2 at the playhead, or that none was recorded for this moment.
 */
import {
  SIM_CAPTURE_L2_NONE_TITLE,
  SIM_CAPTURE_L2_TITLE,
  SIM_REPLAY_L2_CHIP_LABEL,
  SIM_REPLAY_L2_CHIP_VALUE,
  SIM_REPLAY_L2_RECORDED_VALUE,
} from './simConstants';
import type { SimClockState } from './simClockTypes';

/** The recording holds a book for the playhead: it recorded Level 2 at all, and this moment is covered. */
export function captureDepthRecorded(clock: SimClockState | null | undefined): boolean {
  const loaded = clock?.replay_load?.l2_loaded ?? 0;
  return loaded > 0 && clock?.replay_quote?.covered !== false;
}

export function CaptureReplayL2Chip({ clock }: { clock: SimClockState | null | undefined }) {
  const recorded = captureDepthRecorded(clock);
  return (
    <span
      className={`sv-shortability-chip sv-shortability-chip--${recorded ? 'ok' : 'unknown'}`}
      title={recorded ? SIM_CAPTURE_L2_TITLE : SIM_CAPTURE_L2_NONE_TITLE}
      data-testid="capture-l2-chip"
    >
      <span className="sv-shortability-chip__label">{SIM_REPLAY_L2_CHIP_LABEL}</span>
      <span className="sv-shortability-chip__value">
        {recorded ? SIM_REPLAY_L2_RECORDED_VALUE : SIM_REPLAY_L2_CHIP_VALUE}
      </span>
    </span>
  );
}
