/** The read-out that unlocks Strategy (Bot-Trading-Plan §2g, backend setup_scanner/readout.py). */
import {
  BOT_READOUT_RULE,
  BOT_READOUT_STATE_LABELS,
  BOT_READOUT_TITLE,
  BOT_SETUP_RESEARCH,
} from '../constantGroups/bot';
import { BOTS_READOUT_GO_SO_FAR, BOTS_READOUT_UNREPORTED, BOTS_READOUT_VS } from '../constantGroups/bots_page';
import { fmtR, readoutProgress } from './botsPageFormat';
import type { BotReadout as Readout } from './types';

/** The element the hero's "first pullback not proven yet" chip scrolls to. */
export const BOTS_READOUT_ANCHOR = 'bots-readout';

export function BotReadout({ readout }: { readout: Readout | undefined }) {
  if (!readout) {
    return <div className="bots-readout" id={BOTS_READOUT_ANCHOR} data-testid="bots-readout">{BOTS_READOUT_UNREPORTED}</div>;
  }
  const min = readout.rules?.min_go ?? 50;
  const minR = readout.rules?.min_net_r ?? 0.2;
  const tone = (v: number | null | undefined) => (v == null ? '' : v > 0 ? ' is-up' : v < 0 ? ' is-down' : '');
  const barsAlone = BOT_SETUP_RESEARCH.first_pullback?.detail ?? '';
  return (
    <div className={`bots-readout bots-readout--${readout.state}`} id={BOTS_READOUT_ANCHOR} data-testid="bots-readout"
      title={`${BOT_READOUT_RULE} ${readout.reason}`}>
      <div className="bots-readout__head">
        <b>{BOT_READOUT_TITLE}</b>
        <span className="bots-readout__state">{BOT_READOUT_STATE_LABELS[readout.state] ?? readout.state}</span>
        <span className="bots-readout__count">
          <b data-testid="bots-readout-count">{readout.go.triggered} / {min}</b> go setups triggered
        </span>
      </div>
      <div className="bots-readout__bar"><i style={{ width: `${readoutProgress(readout)}%` }} /></div>
      <div className="bots-readout__nums">
        <span>
          {BOTS_READOUT_GO_SO_FAR} <b className={tone(readout.go.avg_net_r)}>{fmtR(readout.go.avg_net_r)}</b>{' '}
          {BOTS_READOUT_VS} <b className={tone(readout.control.avg_net_r)}>{fmtR(readout.control.avg_net_r)}</b>
          {' · '}needs &gt; +{minR.toFixed(1)}R and above blind / wait
        </span>
        <span className="bots-readout__research">{barsAlone}</span>
      </div>
    </div>
  );
}
