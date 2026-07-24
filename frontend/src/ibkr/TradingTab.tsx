/**
 * TradingTab — root component for the IBKR Trading tab.
 *
 * Layout:
 *   Left column  : DepthLadder (Level 2 / L1 fallback)
 *   Center column: OrderTicket + positions/orders
 *   Top bar      : connection status + data source label
 *
 * When IBKR is not connected the tab renders a friendly setup guide.
 * Scanner tabs still need Gateway for live IBKR discovery.
 */
import { useCallback, useState } from 'react';
import { ClosedOrdersModule } from '../closed_orders';
import { LatencyDashboard } from '../execution_latency';
import {
  CLOSED_ORDERS_MODULE_ID,
  IBKR_PAPER_PORT,
  IBKR_LIVE_PORT,
  IBKR_MAX_DEPTH_SYMBOLS,
} from '../constants';
import { useModuleVisibility } from '../workspace';
import { useIbkrStatus } from './useIbkrStatus';
import { useIbkrAccount } from './useIbkrAccount';
import { DepthLadder } from './DepthLadder';
import { OrderTicket } from './OrderTicket';
import { PaperTradingBanner } from './PaperTradingBanner';
import { PositionsPanel } from './PositionsPanel';
import { ReportsTab } from '../reports/ReportsTab';
import { alertApp } from '../ux';
import { cancelIbkrOrderWithFeedback } from './cancelOrder';
import { confirmAndFillWorkingOrder } from './fillWorkingOrderImmediately';
import type { PlaceOrderResult } from './placeOrder';
import {
  TradingSectionNav,
  type TradingTabSection,
} from './TradingSectionNav';
import type { IbkrOrder } from './types';

interface TradingTabProps {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  /** Reports is nested under the Account header, not a top-level tab (see workspace/registry.ts). */
  initialSection?: TradingTabSection;
}

export function TradingTab({
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  initialSection = 'overview',
}: TradingTabProps) {
  const [section, setSection] = useState<TradingTabSection>(initialSection);
  const status = useIbkrStatus();
  const {
    summary,
    positions,
    orders,
    error: accountError,
    refresh,
  } = useIbkrAccount(status.connected);
  const { isVisible } = useModuleVisibility();
  const [depthSymbol, setDepthSymbol] = useState<string | null>(null);
  const [depthInput, setDepthInput] = useState('');
  const [highlightOrderId, setHighlightOrderId] = useState<number | null>(null);

  const handleCancelOrder = useCallback(async (orderId: number) => {
    await cancelIbkrOrderWithFeedback(orderId, refresh);
  }, [refresh]);

  const handleFillImmediately = useCallback(async (order: IbkrOrder) => {
    const res = await confirmAndFillWorkingOrder(order);
    if (res.ok && res.place_order_id != null) {
      setHighlightOrderId(res.place_order_id);
    }
    if (!res.ok && res.error !== 'Fill now cancelled') {
      void alertApp({ title: 'Fill now failed', message: res.error, tone: 'danger' });
    }
    refresh();
  }, [refresh]);

  const handleOrderPlaced = useCallback(
    (result: PlaceOrderResult) => {
      if (result.ok && result.order_id != null) {
        setHighlightOrderId(result.order_id);
      }
      refresh();
    },
    [refresh],
  );

  const modeColor =
    status.mode === 'live' ? 'var(--red)' :
    status.mode === 'paper' ? 'var(--green)' :
    'var(--text-muted)';

  return (
    <div className="ibkr-trading-tab">
      <PaperTradingBanner mode={status.mode} />
      {/* ── Section toggle: Reports is nested here, not a top-level tab ── */}
      <TradingSectionNav section={section} onChange={setSection} />
      {section === 'reports' ? (
        <ReportsTab />
      ) : section === 'latency' ? (
        <LatencyDashboard />
      ) : (
      <>
      {/* ── Status bar ─────────────────────────────────────────────────── */}
      <div className="ibkr-status-bar">
        <span className="ibkr-source-label">Data: Interactive Brokers</span>
        <span className="ibkr-connection-dot" style={{ background: status.connected ? 'var(--green)' : 'var(--text-muted)' }} />
        <span style={{ color: modeColor, fontWeight: 600, textTransform: 'uppercase', fontSize: '0.8rem' }}>
          {status.mode}
        </span>
        {status.connected && (
          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginLeft: 8 }}>
            IB Gateway connected
          </span>
        )}
        {status.connected && (
          <span
            style={{
              marginLeft: 12,
              fontSize: '0.75rem',
              fontWeight: 700,
              color: status.spend_status === 'locked' || status.spend_status === 'locked_live_unconfirmed'
                ? 'var(--green)'
                : 'var(--red)',
            }}
            title="Orders are gated by ibkr/safety.py (IBKR_ORDERS_ENABLED + live confirmation)"
          >
            {status.spend_status === 'locked' || status.spend_status === 'locked_live_unconfirmed'
              ? 'ORDERS LOCKED — no spends'
              : status.spend_status === 'live_armed'
                ? 'LIVE ORDERS ARMED'
                : status.spend_status === 'paper_armed'
                  ? 'PAPER ORDERS ON'
                  : ''}
          </span>
        )}
      </div>

      {/* ── Not connected / not enabled: setup guide ───────────────────── */}
      {!status.connected && (
        <div className="ibkr-disconnected-guide">
          <h3>Interactive Brokers not connected</h3>
          <p>
            Scanner tabs (gappers/movers) also need IB Gateway logged in.
            To use trading features, follow these steps:
          </p>
          <ol>
            <li>
              Download and run <strong>IB Gateway</strong> (offline version) from
              {' '}<a href="https://www.interactivebrokers.com/en/index.php?f=16457" target="_blank" rel="noreferrer">
                interactivebrokers.com
              </a>.
            </li>
            <li>
              Log in with your paper trading credentials. Complete the IBKR Mobile
              2FA prompt (required once per week after Sunday 1 AM ET).
            </li>
            <li>
              In Gateway: <em>Configure → Settings → API → Settings</em>
              <ul>
                <li>Check <strong>Enable ActiveX and Socket Clients</strong></li>
                <li>Add <code>127.0.0.1</code> to Trusted IPs</li>
                <li>Uncheck <strong>Read-Only API</strong> (needed for paper orders)</li>
                <li>Paper port: <code>{IBKR_PAPER_PORT}</code> / Live port: <code>{IBKR_LIVE_PORT}</code></li>
              </ul>
            </li>
            <li>
              Set <code>IBKR_ENABLED=true</code> in your <code>.env</code> file
              and restart Nova. For live trading also add{' '}
              <code>IBKR_LIVE_TRADING_CONFIRMED=true</code>.
            </li>
          </ol>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Nova will reconnect automatically once Gateway is running.
          </p>
          {isVisible(CLOSED_ORDERS_MODULE_ID) && (
            <div
              className="ibkr-account-col ibkr-account-col--offline-preview"
              data-testid="trading-closed-orders-host"
            >
              <ClosedOrdersModule
                selectedSymbol={selectedSymbol}
                onSelectSymbol={onSelectSymbol}
                onOpenTrading={onOpenTrading}
              />
            </div>
          )}
        </div>
      )}

      {/* ── Trading UI (shown only when connected) ─────────────────────── */}
      {status.connected && (
        <div className="ibkr-trading-layout">
          {/* Left: depth ladder */}
          <div className="ibkr-depth-col">
            <h4 className="ibkr-section-title">
              Level {status.mode !== 'disconnected' ? '2' : '1'} Order Book
              {' '}<span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                (max {IBKR_MAX_DEPTH_SYMBOLS} symbols)
              </span>
            </h4>
            <div className="ibkr-depth-symbol-row">
              <input
                className="ibkr-input"
                placeholder="Symbol (e.g. AAPL)"
                value={depthInput}
                onChange={e => setDepthInput(e.target.value.toUpperCase())}
                maxLength={10}
              />
              <button
                className="ibkr-btn-secondary"
                onClick={() => setDepthSymbol(depthInput || null)}
                disabled={!depthInput}
              >
                View Book
              </button>
            </div>
            <DepthLadder key={depthSymbol ?? 'none'} symbol={depthSymbol} />
          </div>

          {/* Center: order ticket */}
          <div className="ibkr-order-col">
            <OrderTicket
              defaultSymbol={depthSymbol ?? ''}
              mode={status.mode}
              connected={status.connected}
              spendStatus={status.spend_status}
              summary={summary}
              positions={positions}
              onOrderPlaced={handleOrderPlaced}
            />
          </div>

          {/* Right / bottom: positions + working + isolated Closed Orders module */}
          <div className="ibkr-account-col" data-testid="trading-working-orders-host">
            <PositionsPanel
              summary={summary}
              positions={positions}
              orders={orders}
              error={accountError}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={onSelectSymbol}
              onOpenTrading={onOpenTrading}
              onCancelOrder={handleCancelOrder}
              onFillImmediately={handleFillImmediately}
              highlightOrderId={highlightOrderId}
              mode={status.mode}
              connected={status.connected}
              spendStatus={status.spend_status}
              onPositionClosed={refresh}
            />
            {isVisible(CLOSED_ORDERS_MODULE_ID) && (
              <div data-testid="trading-closed-orders-host">
                <ClosedOrdersModule
                  selectedSymbol={selectedSymbol}
                  onSelectSymbol={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                />
              </div>
            )}
          </div>
        </div>
      )}
      </>
      )}
    </div>
  );
}
