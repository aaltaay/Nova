/**
 * Hot strip shown only when IBKR Gateway mode is paper — reduces live/paper confusion.
 */
import { PAPER_TRADING_BANNER_TEXT } from '../constants';
import type { IbkrMode } from './types';
import './paperTradingBanner.css';

interface Props {
  mode: IbkrMode;
}

export function PaperTradingBanner({ mode }: Props) {
  if (mode !== 'paper') return null;
  return (
    <div
      className="paper-trading-banner"
      role="status"
      data-testid="paper-trading-banner"
    >
      {PAPER_TRADING_BANNER_TEXT}
    </div>
  );
}
