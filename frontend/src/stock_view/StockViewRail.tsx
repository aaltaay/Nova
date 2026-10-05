/**
 * Fixed right rail: Stock Quote (stats + L2 + T&S) | drag | Trade ticket | Bot Autonomy card.
 * Horizontal splitter reallocates height between quote/depth and Order Entry.
 * TRADE keeps a min-height floor (depth shrinks first) so Extended Hours stays reachable.
 */
import { useRef, type ComponentProps, type CSSProperties } from 'react';
import { BotAutonomyCard } from '../bot/BotAutonomyCard';
import { ResizeHandle } from '../components/ResizeHandle';
import { useResizableHeight } from '../hooks/useResizableHeight';
import { tickerReady } from '../hooks/tickerStore';
import { useTickerSelect } from '../hooks/useTickerStream';
import type { GatewayStatusFact } from '../ibkr';
import { TickerTradeActionBar } from '../ibkr/TickerTradeActionBar';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from '../ibkr/types';
import type { PlaceOrderResult } from '../ibkr/placeOrder';
import { computeQuoteMetrics } from '../modules';
import { useWorkspace } from '../workspace';
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
  mode: IbkrMode;
  connected: boolean;
  /** Whether `connected: false` is a status answer or an unknown (QA D10, #459). */
  gatewayStatus?: GatewayStatusFact;
  spendStatus?: string;
  accountError?: string | null;
  position: IbkrPosition | null;
  summary: IbkrAccountSummary | null;
  onOrderPlaced: (result?: PlaceOrderResult) => void;
  /** False on live-but-hidden trader tabs. */
  uiActive?: boolean;
}

/**
 * The ticket with the stock's reference price, read here: a new price renders the ticket and nothing
 * else on the rail (#707).
 */
function RailTicket(props: Omit<ComponentProps<typeof TickerTradeActionBar>, 'referencePrice'>) {
  const { discoveryProvider } = useWorkspace();
  const { symbol } = props;
  const referencePrice = useTickerSelect(symbol, (state) =>
    (state.detail && tickerReady(state, symbol) ? computeQuoteMetrics(state.detail, discoveryProvider).mainPrice : null));
  return <TickerTradeActionBar {...props} referencePrice={referencePrice} />;
}

export function StockViewRail({
  symbol,
  mode,
  connected,
  gatewayStatus,
  spendStatus,
  accountError = null,
  position,
  summary,
  onOrderPlaced,
  uiActive = true,
}: Props) {
  // The listing's flags (borrow, the venue) come with the quote, not with a print: the same object across prints.
  const listingIbkr = useTickerSelect(symbol, (state) => state.detail?.listing?.ibkr ?? null);
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
            listingIbkr={listingIbkr}
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
          <RailTicket
            symbol={symbol}
            mode={mode}
            connected={connected}
            gatewayStatus={gatewayStatus}
            spendStatus={spendStatus}
            accountError={accountError}
            position={position}
            summary={summary}
            listingIbkr={listingIbkr}
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
