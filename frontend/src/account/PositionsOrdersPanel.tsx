/**
 * Right bottom -- Positions | Orders (Today) | Fills with Nova's own statuses.
 * Filters are Working / Filled / Canceled / Expired / All with counts;
 * Expired is the DAY order expiry at 20:00 ET and the footer says so.
 */
import { useState } from 'react';
import {
  ACCOUNT_COL_AVG,
  ACCOUNT_COL_COMM,
  ACCOUNT_COL_FEES,
  ACCOUNT_COL_LAST,
  ACCOUNT_COL_MKT_VALUE,
  ACCOUNT_COL_PRICE,
  ACCOUNT_COL_QTY,
  ACCOUNT_COL_SIDE,
  ACCOUNT_COL_SOURCE,
  ACCOUNT_COL_STATUS,
  ACCOUNT_COL_SYMBOL,
  ACCOUNT_COL_TIME,
  ACCOUNT_COL_TYPE,
  ACCOUNT_COL_UNREALIZED,
  ACCOUNT_FILLS_EMPTY,
  ACCOUNT_ORDERS_EMPTY,
  ACCOUNT_ORDER_FILTERS,
  ACCOUNT_ORDER_FILTER_LABELS,
  ACCOUNT_POSITIONS_EMPTY,
  ACCOUNT_POS_FOOT,
  ACCOUNT_POS_FOOT_LIVE,
  ACCOUNT_POS_TAB_FILLS,
  ACCOUNT_POS_TAB_ORDERS,
  ACCOUNT_POS_TAB_POSITIONS,
  type AccountOrderFilter,
} from '../constantGroups/account_page';
import { formatOrderStatus } from '../ibkr/orderDisplay';
import type { IbkrOrder } from '../ibkr/types';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { EstChip, Money, etTime, etTimeIso } from './accountBits';
import { sourceKind, sourceLabel } from './accountFigures';
import type { HistoryFill } from './accountHistoryTypes';
import type { AccountPosition } from './accountPositions';

export type PosTab = 'positions' | 'orders' | 'fills';

interface Props {
  practice: boolean;
  positions: AccountPosition[];
  working: IbkrOrder[];
  closed: IbkrOrder[];
  fills: HistoryFill[];
}

export type OrderBucket = 'working' | 'filled' | 'canceled' | 'expired';

/** Nova's own status buckets; `Expired` is the DAY expiry the practice broker stamps. */
export function orderBucket(order: IbkrOrder): OrderBucket {
  const raw = order.status.trim().toLowerCase();
  if (raw === 'expired') return 'expired';
  const label = formatOrderStatus(order.status, order.filled_qty ?? 0, order.qty);
  if (label === 'Filled') return 'filled';
  if (label === 'Cancelled' || label === 'Cancelled (partial fill)' || label === 'Failed') return 'canceled';
  return 'working';
}

export function orderStatusLabel(order: IbkrOrder): string {
  if (order.status.trim().toLowerCase() === 'expired') return 'Expired';
  const label = formatOrderStatus(order.status, order.filled_qty ?? 0, order.qty);
  return label === 'Cancelled' ? 'Canceled' : label;
}

function orderTs(order: IbkrOrder): number {
  const iso = order.filled_at ?? order.updated_at ?? order.submitted_at ?? null;
  const ms = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(ms) ? ms : 0;
}

export function PositionsOrdersPanel({ practice, positions, working, closed, fills }: Props) {
  const [tab, setTab] = useState<PosTab>('orders');
  const [filter, setFilter] = useState<AccountOrderFilter>('all');
  const seen = new Set<number>();
  const orders = [...working, ...closed]
    .filter((o) => (seen.has(o.order_id) ? false : (seen.add(o.order_id), true)))
    .sort((a, b) => orderTs(b) - orderTs(a));
  const fillSource = new Map(fills.map((f) => [f.order_id, f] as const));
  const count = (bucket: AccountOrderFilter): number =>
    bucket === 'all' ? orders.length : orders.filter((o) => orderBucket(o) === bucket).length;
  const shown = filter === 'all' ? orders : orders.filter((o) => orderBucket(o) === filter);
  const sortedFills = [...fills].sort((a, b) => b.ts - a.ts);
  const tabs: Array<[PosTab, string, number]> = [
    ['positions', ACCOUNT_POS_TAB_POSITIONS, positions.filter((p) => p.qty !== 0).length],
    ['orders', ACCOUNT_POS_TAB_ORDERS, orders.length],
    ['fills', ACCOUNT_POS_TAB_FILLS, fills.length],
  ];

  return (
    <section className="acct-panel acct-panel--pos" data-testid="account-positions-orders">
      <div className="acct-panel__head">
        <div className="acct-ptabs" role="tablist">
          {tabs.map(([id, label, n]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} className={`acct-ptabs__item${tab === id ? ' is-on' : ''}`} data-testid={`account-pos-tab-${id}`} onClick={() => setTab(id)}>
              {label} <span className="acct-muted">{n}</span>
            </button>
          ))}
        </div>
      </div>
      {tab === 'orders' && (
        <div className="acct-filters" data-testid="account-order-filters">
          {ACCOUNT_ORDER_FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} className={`acct-filters__item${filter === f ? ' is-on' : ''}`} data-testid={`account-order-filter-${f}`} onClick={() => setFilter(f)}>
              {ACCOUNT_ORDER_FILTER_LABELS[f]}<b>{count(f)}</b>
            </button>
          ))}
        </div>
      )}
      <div className="acct-scroll">
        {tab === 'positions' && (
          <table className="acct-table" data-testid="account-positions-table">
            <thead><tr><th>{ACCOUNT_COL_SYMBOL}</th><th className="r">{ACCOUNT_COL_QTY}</th><th className="r">{ACCOUNT_COL_AVG}</th><th className="r">{ACCOUNT_COL_LAST}</th><th className="r">{ACCOUNT_COL_MKT_VALUE}</th><th className="r">{ACCOUNT_COL_UNREALIZED}</th></tr></thead>
            <tbody>
              {positions.filter((p) => p.qty !== 0).length === 0 ? (
                <tr><td colSpan={6} className="acct-muted">{ACCOUNT_POSITIONS_EMPTY}</td></tr>
              ) : positions.filter((p) => p.qty !== 0).map((p) => (
                <tr key={p.symbol} data-testid={`account-position-${p.symbol}`}>
                  <td>{p.symbol}</td>
                  <td className="r acct-num">{formatShareQty(p.qty)}</td>
                  <td className="r acct-num">{p.avgCost == null ? '—' : p.avgCost.toFixed(4)}{p.estimated && p.avgCost != null && <EstChip />}</td>
                  <td className="r acct-num">{p.mark == null ? '—' : p.mark.toFixed(2)}</td>
                  <td className="r"><Money value={p.marketValue} /></td>
                  <td className="r"><Money value={p.unrealized} signed /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === 'orders' && (
          <table className="acct-table" data-testid="account-orders-table">
            <thead><tr><th>{ACCOUNT_COL_TIME}</th><th>{ACCOUNT_COL_SYMBOL}</th><th>{ACCOUNT_COL_SIDE}</th><th className="r">{ACCOUNT_COL_QTY}</th><th>{ACCOUNT_COL_TYPE}</th><th className="r">{ACCOUNT_COL_PRICE}</th><th>{ACCOUNT_COL_STATUS}</th><th>{ACCOUNT_COL_SOURCE}</th></tr></thead>
            <tbody>
              {shown.length === 0 ? (
                <tr><td colSpan={8} className="acct-muted">{ACCOUNT_ORDERS_EMPTY}</td></tr>
              ) : shown.map((o) => {
                const bucket = orderBucket(o);
                const fill = fillSource.get(o.order_id);
                const price = o.avg_fill_price ?? o.limit_price ?? o.stop_price ?? null;
                return (
                  <tr key={`${o.order_id}-${o.perm_id ?? ''}`} data-testid={`account-order-${o.order_id}`} data-bucket={bucket}>
                    <td className="acct-num">{etTimeIso(o.filled_at ?? o.updated_at ?? o.submitted_at)}</td>
                    <td>{o.symbol}</td>
                    <td className={o.side === 'BUY' ? 'acct-side--buy' : 'acct-side--sell'}>{o.side}</td>
                    <td className="r acct-num">{formatShareQty(o.qty)}</td>
                    <td>{o.order_type}</td>
                    <td className={`r acct-num${bucket === 'canceled' || bucket === 'expired' ? ' acct-muted' : ''}`}>
                      {price == null ? 'MKT' : price.toFixed(2)}{bucket === 'filled' && (o.fill_estimated || practice) && <EstChip />}
                    </td>
                    <td className={bucket === 'filled' || bucket === 'working' ? '' : 'acct-muted'}>{orderStatusLabel(o)}</td>
                    <td className={`acct-src${fill && sourceKind(fill.source) === 'bot' ? ' is-bot' : ''}`}>
                      {fill ? sourceLabel(fill.source, fill.bot_id) : o.source === 'ib_recovered' ? 'IBKR' : o.source === 'nova' ? 'Nova' : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {tab === 'fills' && (
          <table className="acct-table" data-testid="account-fills-table">
            <thead><tr><th>{ACCOUNT_COL_TIME}</th><th>{ACCOUNT_COL_SYMBOL}</th><th>{ACCOUNT_COL_SIDE}</th><th className="r">{ACCOUNT_COL_QTY}</th><th className="r">{ACCOUNT_COL_PRICE}</th><th className="r">{ACCOUNT_COL_COMM}</th><th className="r">{ACCOUNT_COL_FEES}</th><th>{ACCOUNT_COL_SOURCE}</th></tr></thead>
            <tbody>
              {sortedFills.length === 0 ? (
                <tr><td colSpan={8} className="acct-muted">{ACCOUNT_FILLS_EMPTY}</td></tr>
              ) : sortedFills.map((f, i) => (
                <tr key={`${f.order_id}-${f.ts}-${i}`} data-testid={`account-fill-${f.order_id}`}>
                  <td className="acct-num">{etTime(f.ts)}</td>
                  <td>{f.symbol}</td>
                  <td className={f.side === 'BUY' ? 'acct-side--buy' : 'acct-side--sell'}>{f.side}</td>
                  <td className="r acct-num">{formatShareQty(f.qty)}</td>
                  <td className="r acct-num">{f.price.toFixed(2)}<EstChip /></td>
                  <td className="r acct-num">{formatMoney(f.commission)}</td>
                  <td className="r acct-num">{formatMoney(f.fees)}</td>
                  <td className={`acct-src${sourceKind(f.source) === 'bot' ? ' is-bot' : ''}`}>{sourceLabel(f.source, f.bot_id)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="acct-foot">{practice ? ACCOUNT_POS_FOOT : ACCOUNT_POS_FOOT_LIVE}</p>
    </section>
  );
}
