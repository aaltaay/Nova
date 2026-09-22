/**
 * Fixed right rail: Stock Quote (stats + L2 + T&S) | drag | Trade ticket | Bot Autonomy card.
 * Horizontal splitter reallocates height between quote/depth and Order Entry.
 * TRADE keeps a min-height floor (depth shrinks first) so Extended Hours stays reachable.
 */
import { useRef, type CSSProperties } from 'react';
import { BotAutonomyCard } from '../bot/BotAutonomyCard';
import { ResizeHandle } from '../components/ResizeHandle';
import { useResizableHeight } from '../hooks/useResizableHeight';
import { TickerTradeActionBar } from '../ibkr/TickerTradeActionBar';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from '../ibkr/types';
import type { PlaceOrderResult } from '../ibkr/placeOrder';
import type { TickerDetail } from '../types/ticker';
import {
  STOCK_VIEW_DEPTH_ORDER_SPLIT_KEY,
  STOCK_VIEW_DEPTH_ORDER_SPLIT_MAX_PCT,
  STOCK_VIEW_DEPTH_ORDER_SPLIT_MIN_PCT,
  STOCK_VIEW_DEPTH_ORDER_SPLIT_PCT,
  STOCK_VIEW_DEPTH_PANE_MIN_PX,
  STOCK_VIEW_ORDER_PANE_MIN_PX,
  STOCK_VIEW_TITLE,
} from '../constants';
import { StockViewDepthTape } from './StockViewDepthTape';
import { StockViewModuleCard } from './StockViewModuleCard';

interface Props {
  symbol: string;
  detail: TickerDetail;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  accountError?: string | null;
  position: IbkrPosition | null;
  summary: IbkrAccountSummary | null;
  referencePrice: number | null;
  onOrderPlaced: (result?: PlaceOrderResult) => void;
  /** False on live-but-hidden trader tabs. */
  uiActive?: boolean;
}

export function StockViewRail({
  symbol,
  detail,
  mode,
  connected,
  spendStatus,
  accountError = null,
  position,
  summary,
  referencePrice,
  onOrderPlaced,
  uiActive = true,
}: Props) {
  const tradeStackRef = useRef<HTMLDivElement>(null);
  const { topPct, onDragStart, reset } = useResizableHeight({
    storageKey: STOCK_VIEW_DEPTH_ORDER_SPLIT_KEY,
    defaultPct: STOCK_VIEW_DEPTH_ORDER_SPLIT_PCT,
    minPct: STOCK_VIEW_DEPTH_ORDER_SPLIT_MIN_PCT,
    maxPct: STOCK_VIEW_DEPTH_ORDER_SPLIT_MAX_PCT,
    containerRef: tradeStackRef,
  });

  return (
    <aside
      className="stock-view-quote sv-rail"
      aria-label={STOCK_VIEW_TITLE}
      data-testid="stock-view-rail"
    >
      <div
        ref={tradeStackRef}
        className="sv-rail__trade-stack"
        data-testid="stock-view-trade-stack"
        style={
          {
            ['--sv-depth-pct']: `${topPct}%`,
            ['--sv-depth-pane-min']: `${STOCK_VIEW_DEPTH_PANE_MIN_PX}px`,
            ['--sv-order-pane-min']: `${STOCK_VIEW_ORDER_PANE_MIN_PX}px`,
          } as CSSProperties
        }
      >
        <div className="sv-rail__depth" data-testid="stock-view-depth-slot">
          <StockViewDepthTape
            selectedSymbol={symbol}
            detail={detail}
            listingIbkr={detail.listing?.ibkr ?? null}
            uiActive={uiActive}
          />
        </div>

        <ResizeHandle
          orientation="horizontal"
          onPointerDown={onDragStart}
          onDoubleClick={reset}
          label="Resize Stock Quote and Order Entry"
        />

        {/* No card title: the compact ticket's own header reads TRADE · SYM · venue. */}
        <StockViewModuleCard
          className="sv-open-card"
          testId="stock-view-open-card"
          aria-label="Trade order"
        >
          <TickerTradeActionBar
            symbol={symbol}
            mode={mode}
            connected={connected}
            spendStatus={spendStatus}
            accountError={accountError}
            position={position}
            summary={summary}
            referencePrice={referencePrice}
            listingIbkr={detail.listing?.ibkr ?? null}
            onOrderPlaced={onOrderPlaced}
            variant="rail"
          />
        </StockViewModuleCard>
      </div>
      {/* Bot Autonomy: a quiet card at the bottom of the rail, not a bar over the page. */}
      <BotAutonomyCard />
    </aside>
  );
}
