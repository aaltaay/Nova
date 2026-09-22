/**
 * Level 2 during historical replay (#309).
 *
 * An IBKR historical download carries trades only, so the book here comes from
 * the local depth recorder (`backend/l2/`) when one of its sessions covered
 * this playhead second, and from nowhere at all when none did -- which is the
 * common case. Both states are stated plainly: a recorded book is drawn in the
 * live montage and labelled with the second it was recorded at, and an
 * unrecorded moment says so inside the ladder rather than leaving an empty one
 * that reads like a vanished market. The live depth feed is never mounted; it
 * would paint today's book over a past session.
 *
 * (The rail hides .ibkr-depth-fallback-badge, so the notes use their own class.)
 */
import { MontageSide } from '../ibkr';
import { etTime } from './historicalReplayFormat';
import {
  SIM_REPLAY_L2_CHIP_LABEL,
  SIM_REPLAY_L2_CHIP_TITLE,
  SIM_REPLAY_L2_CHIP_VALUE,
  SIM_REPLAY_L2_EMPTY_NOTE,
  SIM_REPLAY_L2_RECORDED_TITLE,
  SIM_REPLAY_L2_RECORDED_VALUE,
} from './simConstants';
import type { HistoricalDepthBook } from './historicalTypes';
import { useHistoricalDepthLine } from './useHistoricalDepthLine';

interface Props {
  /** The recorded book at the playhead, or null when none was recorded. */
  depth?: HistoricalDepthBook | null;
  /**
   * The loaded historical window's symbol when this panel is its Level 2: the
   * panel then holds the replay depth slot a bot's gate reads (QA R44). A
   * capture gap renders this panel without one.
   */
  holdLineFor?: string | null;
}

export function HistoricalDepth({ depth = null, holdLineFor = null }: Props) {
  useHistoricalDepthLine(holdLineFor ?? '', Boolean(holdLineFor));
  return (
    <div className="das-l2" data-testid="historical-l2" data-depth-source={depth?.source ?? 'none'}>
      {depth ? (
        <div className="sim-replay-l2-note" data-testid="historical-l2-recorded">
          Recorded book at {etTime(depth.ts)} ET
        </div>
      ) : (
        <div
          className="sim-replay-l2-note sim-replay-l2-note--empty"
          data-testid="historical-l2-empty"
          title={SIM_REPLAY_L2_CHIP_TITLE}
        >
          {SIM_REPLAY_L2_EMPTY_NOTE}
        </div>
      )}
      <div className="das-l2-montage">
        <MontageSide side="bid" levels={depth?.bids ?? []} />
        <MontageSide side="ask" levels={depth?.asks ?? []} />
      </div>
    </div>
  );
}

/** Stands in for the live halt / shortability chips in the Level 2 header. */
export function HistoricalL2Chip({ depth = null }: Props) {
  const recorded = depth != null;
  return (
    <span
      className={`sv-shortability-chip sv-shortability-chip--${recorded ? 'ok' : 'unknown'}`}
      title={recorded ? SIM_REPLAY_L2_RECORDED_TITLE : SIM_REPLAY_L2_CHIP_TITLE}
      data-testid="historical-l2-chip"
    >
      <span className="sv-shortability-chip__label">{SIM_REPLAY_L2_CHIP_LABEL}</span>
      <span className="sv-shortability-chip__value">
        {recorded ? SIM_REPLAY_L2_RECORDED_VALUE : SIM_REPLAY_L2_CHIP_VALUE}
      </span>
    </span>
  );
}
