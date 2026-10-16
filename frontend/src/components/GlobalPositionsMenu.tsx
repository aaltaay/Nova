/**
 * The card under the header's Positions count: each stock held now, its
 * shares (a short says so), average cost and open P&L. A row opens that stock
 * in the Trader; View All Positions opens Account / Trading.
 */
import {
  GLOBAL_BAR_OFFLINE_PLACEHOLDER,
  GLOBAL_BAR_POSITIONS_EMPTY,
  GLOBAL_BAR_POSITIONS_MENU_TITLE,
  GLOBAL_BAR_POSITIONS_OPEN_PNL,
  GLOBAL_BAR_POSITIONS_SHORT,
  GLOBAL_BAR_POSITIONS_STALE_NOTE,
  GLOBAL_BAR_VIEW_ALL_POSITIONS,
  globalBarPositionOpenTitle,
} from '../constantGroups/global_bar';
import { formatMoney } from '../utils/formatMoney';
import { formatSignedMoney, pnlToneClass } from './globalBarMoney';
import type { HeldPositionRow } from './globalPositionsRows';
import { requestOpenTradingTab } from './openTradingTabNav';

interface Props {
  rows: HeldPositionRow[];
  stale: boolean;
  onOpenSymbol: (symbol: string) => void;
  traderActive: boolean;
  closeTraderView: () => void;
  onClose: () => void;
}

export function GlobalPositionsMenu({ rows, stale, onOpenSymbol, traderActive, closeTraderView, onClose }: Props) {
  function handleViewAll() {
    onClose();
    // Latch first so DashboardPage consumes it after Trader unmounts (as View All Orders).
    requestOpenTradingTab();
    if (traderActive) closeTraderView();
  }

  return (
    <div
      className="global-app-bar__card global-app-bar__positions-menu"
      role="menu"
      aria-label={GLOBAL_BAR_POSITIONS_MENU_TITLE}
      data-testid="global-positions-menu"
    >
      {stale && <p className="global-app-bar__card-note">{GLOBAL_BAR_POSITIONS_STALE_NOTE}</p>}
      {rows.length === 0 ? (
        <div className="global-app-bar__card-row is-empty" data-testid="global-positions-empty">
          <span>{GLOBAL_BAR_POSITIONS_EMPTY}</span>
          <span />
        </div>
      ) : (
        rows.map((r) => (
          <button
            key={r.symbol}
            type="button"
            role="menuitem"
            className="global-app-bar__position-row"
            title={globalBarPositionOpenTitle(r.symbol)}
            data-testid={`global-position-${r.symbol}`}
            onClick={() => {
              onClose();
              onOpenSymbol(r.symbol);
            }}
          >
            <span className="global-app-bar__position-symbol">{r.symbol}</span>
            <span className="global-app-bar__position-qty">
              {Math.abs(r.qty).toLocaleString('en-US')}
              {r.qty < 0 && <em> {GLOBAL_BAR_POSITIONS_SHORT}</em>}
              {r.avgCost != null && <> @ {formatMoney(r.avgCost)}</>}
            </span>
            <span
              className={`global-app-bar__position-pnl ${pnlToneClass(r.openPnl)}`}
              title={GLOBAL_BAR_POSITIONS_OPEN_PNL}
            >
              {r.openPnl == null ? GLOBAL_BAR_OFFLINE_PLACEHOLDER : formatSignedMoney(r.openPnl)}
            </span>
          </button>
        ))
      )}

      <div className="global-app-bar__menu-divider" aria-hidden />
      <button
        type="button"
        className="global-app-bar__menu-action"
        role="menuitem"
        data-testid="global-positions-view-all"
        onClick={handleViewAll}
      >
        {GLOBAL_BAR_VIEW_ALL_POSITIONS}
      </button>
    </div>
  );
}
