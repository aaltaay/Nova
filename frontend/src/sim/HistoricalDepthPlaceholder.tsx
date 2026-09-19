/**
 * Level 2 during historical replay: the live montage frame with no levels, and
 * a header chip saying why. Historical depth is not recorded, and the live
 * depth feed must not paint today's book over a past session. (The rail hides
 * .ibkr-depth-fallback-badge, so the explanation lives in the header chip.)
 */
import { MontageSide } from '../ibkr';
import { SIM_REPLAY_L2_CHIP_LABEL, SIM_REPLAY_L2_CHIP_TITLE, SIM_REPLAY_L2_CHIP_VALUE } from './simConstants';

export function HistoricalDepthPlaceholder() {
  return (
    <div className="das-l2" data-testid="historical-l2">
      <div className="das-l2-montage">
        <MontageSide side="bid" levels={[]} />
        <MontageSide side="ask" levels={[]} />
      </div>
    </div>
  );
}

/** Stands in for the live halt / shortability chips in the Level 2 header. */
export function HistoricalL2Chip() {
  return (
    <span
      className="sv-shortability-chip sv-shortability-chip--unknown"
      title={SIM_REPLAY_L2_CHIP_TITLE}
      data-testid="historical-l2-chip"
    >
      <span className="sv-shortability-chip__label">{SIM_REPLAY_L2_CHIP_LABEL}</span>
      <span className="sv-shortability-chip__value">{SIM_REPLAY_L2_CHIP_VALUE}</span>
    </span>
  );
}
