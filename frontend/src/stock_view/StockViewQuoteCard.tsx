/** Dense quote stats for Stock View — wrapped in shared module card (standalone uses). */
import {
  STOCK_VIEW_MODULE_QUOTE_TITLE,
} from '../constants';
import type { TickerDetail } from '../types/ticker';
import { StockViewModuleCard } from './StockViewModuleCard';
import { StockViewQuotePrice } from './StockViewQuotePrice';
import { StockViewQuoteStats } from './StockViewQuoteStats';

interface Props {
  detail: TickerDetail;
  /** When true, omit last/change (tests / callers that already show price). */
  hidePrice?: boolean;
}

export function StockViewQuoteCard({ detail, hidePrice = false }: Props) {
  return (
    <StockViewModuleCard
      title={STOCK_VIEW_MODULE_QUOTE_TITLE}
      className="sv-quote-card"
      testId="stock-view-quote-card"
      aria-label="Stock Quote"
    >
      <div data-module="stock-view-quote">
        {!hidePrice && <StockViewQuotePrice detail={detail} />}
        <StockViewQuoteStats detail={detail} />
      </div>
    </StockViewModuleCard>
  );
}
