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
import { MontageSide, bookPeak } from '../ibkr';
import { etTime } from './historicalReplayFormat';
import { useMassiveDay } from './massiveDaysStore';
import {
  SIM_REPLAY_L2_CHIP_LABEL,
  SIM_REPLAY_L2_CHIP_TITLE,
  SIM_REPLAY_L2_CHIP_VALUE,
  SIM_REPLAY_L2_EMPTY_NOTE,
  SIM_REPLAY_L2_NBBO_ARRIVED,
  SIM_REPLAY_L2_NBBO_MISSING,
  SIM_REPLAY_L2_NBBO_NONE,
  SIM_REPLAY_L2_NBBO_TITLE,
  SIM_REPLAY_L2_NBBO_VALUE,
  SIM_REPLAY_L2_RECORDED_TITLE,
  SIM_REPLAY_L2_RECORDED_VALUE,
  simReplayL2NbboNote,
} from './simConstants';
import { isMassive, type HistoricalDepthBook } from './historicalTypes';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import { useHistoricalDepthLine } from './useHistoricalDepthLine';

/** A Massive window's best bid and ask as a one-level ladder (ADR 046), never a recorded book. */
export const MASSIVE_NBBO_SOURCE = 'massive_nbbo';

interface Props {
  /** The recorded book at the playhead (or a Massive window's NBBO), or null when there is none. */
  depth?: HistoricalDepthBook | null;
  /**
   * The loaded historical window's symbol when this panel is its Level 2: the
   * panel then holds the replay depth slot a bot's gate reads (QA R44). A
   * capture gap renders this panel without one.
   */
  holdLineFor?: string | null;
  /** The replay snapshot, so a Massive window can say why it has no quote. */
  snapshot?: HistoricalSnapshot | null;
}

/** Why a Massive window shows no bid/ask here; null when it shows one, or the window is not Massive. */
function useMassiveQuoteNote(snapshot: HistoricalSnapshot | null | undefined, depth: HistoricalDepthBook | null): string | null {
  const massive = isMassive(snapshot?.selection);
  const missing = massive && depth == null && snapshot?.quote_status === 'not_downloaded';
  // Only a window still missing its bid/ask asks whether the day's quotes have landed since.
  const day = useMassiveDay(missing ? snapshot?.selection?.date : null, missing);
  if (!massive || depth != null) return null;
  if (snapshot?.quote_status === 'not_downloaded') return day?.quotes ? SIM_REPLAY_L2_NBBO_ARRIVED : SIM_REPLAY_L2_NBBO_MISSING;
  return snapshot?.selection?.trade_count ? SIM_REPLAY_L2_NBBO_NONE : null;
}

export function HistoricalDepth({ depth = null, holdLineFor = null, snapshot = null }: Props) {
  useHistoricalDepthLine(holdLineFor ?? '', Boolean(holdLineFor));
  const massiveNote = useMassiveQuoteNote(snapshot, depth);
  const bids = depth?.bids ?? [];
  const asks = depth?.asks ?? [];
  const peak = bookPeak(bids, asks);
  const nbbo = depth?.source === MASSIVE_NBBO_SOURCE;
  return (
    <div className="das-l2" data-testid="historical-l2" data-depth-source={depth?.source ?? 'none'}>
      {depth ? (
        <div className="sim-replay-l2-note" data-testid={nbbo ? 'historical-l2-nbbo' : 'historical-l2-recorded'}
          title={nbbo ? SIM_REPLAY_L2_NBBO_TITLE : undefined}>
          {nbbo ? simReplayL2NbboNote(etTime(depth.ts)) : <>Recorded book at {etTime(depth.ts)} ET</>}
        </div>
      ) : (
        <div
          className="sim-replay-l2-note sim-replay-l2-note--empty"
          data-testid="historical-l2-empty"
          title={massiveNote ? SIM_REPLAY_L2_NBBO_TITLE : SIM_REPLAY_L2_CHIP_TITLE}
        >
          {massiveNote ?? SIM_REPLAY_L2_EMPTY_NOTE}
        </div>
      )}
      <div className="das-l2-montage">
        <MontageSide side="bid" levels={bids} peak={peak} />
        <MontageSide side="ask" levels={asks} peak={peak} />
      </div>
    </div>
  );
}

/** Stands in for the live halt / shortability chips in the Level 2 header. */
export function HistoricalL2Chip({ depth = null, snapshot = null }: Props) {
  const nbbo = depth?.source === MASSIVE_NBBO_SOURCE || (depth == null && isMassive(snapshot?.selection));
  const recorded = depth != null && !nbbo;
  const title = nbbo ? SIM_REPLAY_L2_NBBO_TITLE : recorded ? SIM_REPLAY_L2_RECORDED_TITLE : SIM_REPLAY_L2_CHIP_TITLE;
  const value = nbbo ? SIM_REPLAY_L2_NBBO_VALUE : recorded ? SIM_REPLAY_L2_RECORDED_VALUE : SIM_REPLAY_L2_CHIP_VALUE;
  return (
    <span
      className={`sv-shortability-chip sv-shortability-chip--${depth != null ? 'ok' : 'unknown'}`}
      title={title}
      data-testid="historical-l2-chip"
    >
      <span className="sv-shortability-chip__label">{SIM_REPLAY_L2_CHIP_LABEL}</span>
      <span className="sv-shortability-chip__value">{value}</span>
    </span>
  );
}
