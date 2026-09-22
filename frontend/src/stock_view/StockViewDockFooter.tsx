/**
 * Drawer footer: `Position SYM +qty @ avg [est] · unrealized ±$x` beside the
 * venue note, readable without switching tabs. The est chip appears only on
 * a practice venue (Paper / Sim), where the average cost came from estimated
 * fills; a missing unrealized figure is a dash, never a guess. With no symbol
 * selected it says so and counts the open positions (QA W29); on the sample
 * desk the note is the sample label, never a real venue's (W31).
 */
import {
  DRAWER_LIVE_NOTE,
  DRAWER_NO_POSITION,
  DRAWER_NO_SYMBOL,
  DRAWER_PAPER_NOTE,
  DRAWER_POSITION_LABEL,
  DRAWER_SIM_NOTE,
  DRAWER_UNREALIZED_LABEL,
  DRAWER_UNREALIZED_UNKNOWN,
  drawerOpenPositions,
} from '../constantGroups/trader_chrome';
import type { IbkrMode, IbkrPosition } from '../ibkr/types';
import { SAMPLE_MARKETING_LABEL } from '../sample_data/sampleCopy';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { EstChip } from './EstChip';

type Props = {
  symbol: string;
  mode: IbkrMode;
  position: IbkrPosition | null;
  /** Open positions on the account, for the no-symbol line. */
  openPositions?: number;
};

function signedMoney(value: number): string {
  return `${value < 0 ? '−' : '+'}${formatMoney(Math.abs(value))}`;
}

function venueNote(mode: IbkrMode): string | null {
  if (mode === 'sim') return DRAWER_SIM_NOTE;
  if (mode === 'paper') return DRAWER_PAPER_NOTE;
  if (mode === 'live') return DRAWER_LIVE_NOTE;
  return null;
}

export function StockViewDockFooter({ symbol, mode, position, openPositions = 0 }: Props) {
  const sample = useSampleDataOptional() != null;
  const held = position != null && position.qty !== 0;
  const practice = mode === 'paper' || mode === 'sim';
  const note = sample ? SAMPLE_MARKETING_LABEL : venueNote(mode);
  const pnl = position?.unrealized_pnl;
  const sym = symbol.trim();
  return (
    <footer className="sv-open-orders-dock__foot" data-testid="stock-view-dock-footer">
      <span className="sv-open-orders-dock__foot-pos">
        {held ? (
          <>
            {DRAWER_POSITION_LABEL}{' '}
            <b className={position.qty > 0 ? 'is-up' : 'is-down'}>
              {symbol} {position.qty > 0 ? '+' : ''}
              {formatShareQty(position.qty)} @{' '}
              {position.avg_cost != null ? position.avg_cost.toFixed(2) : DRAWER_UNREALIZED_UNKNOWN}
            </b>
            {practice ? (
              <>
                {' '}
                <EstChip />
              </>
            ) : null}
            {' · '}
            {DRAWER_UNREALIZED_LABEL}{' '}
            <b className={pnl == null ? '' : pnl >= 0 ? 'is-up' : 'is-down'}>
              {pnl == null ? DRAWER_UNREALIZED_UNKNOWN : signedMoney(pnl)}
            </b>
          </>
        ) : sym ? (
          <>
            {DRAWER_NO_POSITION} · {sym}
          </>
        ) : (
          <>
            {DRAWER_NO_SYMBOL} · {drawerOpenPositions(openPositions)}
          </>
        )}
      </span>
      {note && <span className="sv-open-orders-dock__foot-note">{note}</span>}
    </footer>
  );
}
