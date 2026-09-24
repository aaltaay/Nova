/**
 * Compact ticket header (approved Trader redesign, 2026-09-21):
 * `TRADE · SYM · <venue> · fills estimated` with the TIF segmented control on
 * the right. The venue tag is the quote card's own (`StockViewVenueTag`), so
 * the header and the card cannot disagree about what a fill means; Live has
 * no practice tag and is named plainly.
 */
import { STOCK_VIEW_MODULE_OPEN_TITLE } from '../constants';
import {
  TRADE_DEFAULT_TIFS,
  type TradeDefaultTif,
} from '../constantGroups/trade_defaults';
import {
  TICKET_TIF_LABEL,
  TICKET_TIF_TITLE,
  TICKET_VENUE_LIVE,
  TICKET_VENUE_LIVE_TITLE,
} from '../constantGroups/trader_chrome';
import { StockViewVenueTag } from '../stock_view/StockViewVenueTag';
import type { IbkrMode } from './types';

interface Props {
  symbol: string;
  mode: IbkrMode;
  tif: TradeDefaultTif;
  disabled: boolean;
  /** Why `disabled` is set -- each locked TIF button says it (ux/whyTip.ts). */
  why?: string | null;
  onTifChange: (tif: TradeDefaultTif) => void;
}

export function ManualOrderTicketHeader({ symbol, mode, tif, disabled, why = null, onTifChange }: Props) {
  const sym = symbol.trim().toUpperCase();
  const lockWhy = disabled ? why || undefined : undefined;
  return (
    <header className="mot-head" data-testid="manual-order-header">
      <span className="mot-head__title">
        {STOCK_VIEW_MODULE_OPEN_TITLE}
        {sym ? ` · ${sym}` : ''}
      </span>
      {mode === 'live' ? (
        <span
          className="mot-head__live"
          title={TICKET_VENUE_LIVE_TITLE}
          data-testid="manual-order-venue-live"
        >
          {TICKET_VENUE_LIVE}
        </span>
      ) : (
        <StockViewVenueTag symbol={sym} />
      )}
      <div className="mot-head__tools">
        <span className="mot-head__k">{TICKET_TIF_LABEL}</span>
        <div
          className="mot-seg mot-seg--tif"
          role="group"
          aria-label={TICKET_TIF_TITLE}
          title={lockWhy ? undefined : TICKET_TIF_TITLE}
          data-testid="manual-order-tif"
        >
          {TRADE_DEFAULT_TIFS.map((value) => (
            <button
              key={value}
              type="button"
              className={tif === value ? 'is-on' : ''}
              aria-pressed={tif === value}
              disabled={disabled}
              data-why={lockWhy}
              data-testid={`manual-order-tif-${value.toLowerCase()}`}
              onClick={() => onTifChange(value)}
            >
              {value}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
