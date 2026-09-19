/** Hover/click detail card under the GlobalAppBar Net Liq / Day P&L cluster. */
import {
  GLOBAL_BAR_CARD_CASH,
  GLOBAL_BAR_CARD_GPV,
  GLOBAL_BAR_CARD_OPEN_PNL,
  GLOBAL_BAR_CARD_REALIZED_PNL,
  GLOBAL_BAR_OFFLINE_PLACEHOLDER,
} from '../constants';
import type { IbkrAccountSummary } from '../ibkr/types';
import { formatMoney } from '../utils/formatMoney';
import { formatSignedMoney, pnlToneClass } from './globalBarMoney';
import { FundAccountButton } from '../ibkr/FundAccountButton';

interface Props {
  summary: IbkrAccountSummary | null;
}

export function GlobalAccountCard({ summary }: Props) {
  const openPnl = summary?.UnrealizedPnL ?? null;
  const realized = summary?.RealizedPnL ?? null;

  return (
    <div className="global-app-bar__card" role="dialog" aria-label="Account details">
      <div className="global-app-bar__card-row">
        <span>{GLOBAL_BAR_CARD_OPEN_PNL}</span>
        <span className={pnlToneClass(openPnl)}>{formatSignedMoney(openPnl)}</span>
      </div>
      <div className="global-app-bar__card-row">
        <span>{GLOBAL_BAR_CARD_REALIZED_PNL}</span>
        <span className={pnlToneClass(realized)}>{formatSignedMoney(realized)}</span>
      </div>
      <div className="global-app-bar__card-row">
        <span>{GLOBAL_BAR_CARD_CASH}</span>
        <span>
          {summary?.TotalCashValue != null
            ? formatMoney(summary.TotalCashValue)
            : GLOBAL_BAR_OFFLINE_PLACEHOLDER}
        </span>
      </div>
      <div className="global-app-bar__card-row">
        <span>{GLOBAL_BAR_CARD_GPV}</span>
        <span>
          {summary?.GrossPositionValue != null
            ? formatMoney(summary.GrossPositionValue)
            : GLOBAL_BAR_OFFLINE_PLACEHOLDER}
        </span>
      </div>
      <div className="global-app-bar__card-row global-app-bar__card-row--fund">
        <FundAccountButton />
      </div>
    </div>
  );
}
