/**
 * Registry-mountable Closed Orders host (ADR 005 feature slice).
 * TradingTab also mounts this when the module is visible — ready for hide/move.
 */
import { useMemo, useState } from 'react';
import { CLOSED_ORDERS_MODULE_ID } from '../constants';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { ClosedOrdersPanel } from './ClosedOrdersPanel';
import { buildMockClosedOrders } from './mockClosedOrders';
import { useClosedOrders } from './useClosedOrders';

interface Props {
  selectedSymbol?: string | null;
  onSelectSymbol?: (symbol: string) => void;
  onOpenTrading?: (symbol: string) => void;
  filterSymbol?: string | null;
  /** Hide panel title when hosted under Stock View Closed tab. */
  hideTitle?: boolean;
}

export function ClosedOrdersModule({
  selectedSymbol = null,
  onSelectSymbol,
  onOpenTrading,
  filterSymbol = null,
  hideTitle = false,
}: Props) {
  const status = useIbkrStatus();
  const { orders, error } = useClosedOrders(status.connected);
  /** When Gateway has no terminal orders, show paper-style sample until hidden. */
  const [preferSample, setPreferSample] = useState(true);

  // Never substitute sample data for a genuine read failure — that would
  // hide the failure behind fake "success" rows.
  const usingSample = orders.length === 0 && !error && preferSample;
  const rows = useMemo(
    () => (usingSample ? buildMockClosedOrders(filterSymbol ?? selectedSymbol) : orders),
    [usingSample, orders, filterSymbol, selectedSymbol],
  );

  return (
    <section
      className="closed-orders-module"
      data-testid="closed-orders-module"
      data-module-id={CLOSED_ORDERS_MODULE_ID}
    >
      {orders.length === 0 && !error && (
        <div className="ibkr-closed-orders-toolbar">
          <button
            type="button"
            className="ibkr-btn-secondary"
            data-testid="closed-orders-toggle-sample"
            onClick={() => setPreferSample((v) => !v)}
          >
            {preferSample ? 'Hide sample' : 'Show sample'}
          </button>
        </div>
      )}
      <ClosedOrdersPanel
        orders={rows}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={onSelectSymbol}
        onOpenTrading={onOpenTrading}
        filterSymbol={filterSymbol}
        sampleMode={usingSample}
        hideTitle={hideTitle}
        error={error}
      />
    </section>
  );
}
