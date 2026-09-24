/**
 * Right bottom -- Positions | Orders (Today) | Fills with Nova's own statuses.
 * Filters are Working / Filled / Canceled / Expired / All with counts;
 * Expired is the DAY order expiry (20:00 ET on Paper, the replayed window's
 * end on Sim) and the footer says which. Every order row names its own source
 * stamp (QA W9); a working order from an earlier day shows its date (W4). On
 * Live the Fills tab reads IBKR's filled orders (W17).
 */
import { useMemo, useState } from 'react';
import type { DeskVenue } from '../constantGroups/desk_venue';
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
  ACCOUNT_FILLS_FOOT_LIVE,
  ACCOUNT_ORDERS_EMPTY,
  ACCOUNT_ORDER_FILTERS,
  ACCOUNT_ORDER_FILTER_LABELS,
  ACCOUNT_POSITIONS_EMPTY,
  ACCOUNT_POS_FOOT,
  ACCOUNT_POS_FOOT_LIVE,
  ACCOUNT_POS_FOOT_SIM,
  ACCOUNT_POS_TAB_FILLS,
  ACCOUNT_POS_TAB_ORDERS,
  ACCOUNT_POS_TAB_POSITIONS,
  ACCOUNT_PRICE_NONE,
  ACCOUNT_PRICE_NONE_TITLE,
  type AccountOrderFilter,
} from '../constantGroups/account_page';
import { formatOrderStatus, plausiblePrice } from '../ibkr/orderDisplay';
import { orderRowKeys, uniqueOrders } from '../ibkr/orderIdentity';
import type { IbkrOrder } from '../ibkr/types';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { EstChip, Money, etOrderStamp, etTime } from './accountBits';
import { sourceKind, sourceLabel } from './accountFigures';
import type { AccountFillRow } from './accountLive';
import type { AccountPosition } from './accountPositions';

export type PosTab = 'positions' | 'orders' | 'fills';

interface Props {
  practice: boolean;
  /** Which footer the Expired rule reads (Sim: the replayed window's end). */
  venue?: DeskVenue;
  positions: AccountPosition[];
  working: IbkrOrder[];
  closed: IbkrOrder[];
  fills: AccountFillRow[];
  /** Today's practice date (YYYY-MM-DD); rows from another day show their date. */
  today?: string | null;
}

/**
 * The Source cell: the row's own ADR 007 stamp (practice rows carry
 * `order_source` / `bot_id`), else a fill's, else who placed it on Live --
 * never a blanket "Nova" for a working or out-of-range order (QA W9).
 */
export function orderSourceCell(order: IbkrOrder, fill: { source: string | null; botId: string | null } | undefined): { label: string; bot: boolean } {
  const stamped = typeof order.order_source === 'string' && order.order_source ? order.order_source : null;
  const source = stamped ?? fill?.source ?? null;
  const botId = (typeof order.bot_id === 'string' && order.bot_id) || fill?.botId || null;
  if (source) return { label: sourceLabel(source, botId), bot: sourceKind(source) === 'bot' || botId != null };
  if (order.source === 'ib_recovered') return { label: sourceLabel('ibkr', null), bot: false };
  if (order.source === 'nova') return { label: sourceLabel('nova', null), bot: false };
  return { label: '—', bot: false };
}

export type OrderBucket = 'working' | 'filled' | 'canceled' | 'expired';

const isExpired = (order: IbkrOrder): boolean =>
  typeof order.status === 'string' && order.status.trim().toLowerCase() === 'expired';

/** Nova's own status buckets; `Expired` is the DAY expiry the practice broker stamps. */
export function orderBucket(order: IbkrOrder): OrderBucket {
  if (isExpired(order)) return 'expired';
  const label = formatOrderStatus(order.status, order.filled_qty ?? 0, order.qty);
  if (label === 'Filled') return 'filled';
  if (label === 'Cancelled' || label === 'Cancelled (partial fill)' || label === 'Failed') return 'canceled';
  return 'working';
}

export function orderStatusLabel(order: IbkrOrder): string {
  if (isExpired(order)) return 'Expired';
  const label = formatOrderStatus(order.status, order.filled_qty ?? 0, order.qty);
  return label === 'Cancelled' ? 'Canceled' : label;
}

/**
 * PRICE cell: the fill price, else the limit / stop, never IB's unset price
 * (C28); an unfilled market order has no price to show, so "—", not "MKT" --
 * the Type column already says MKT (V32).
 */
export function orderPriceCell(order: IbkrOrder): number | null {
  return (
    plausiblePrice(order.avg_fill_price)
    ?? plausiblePrice(order.limit_price)
    ?? plausiblePrice(order.stop_price)
  );
}

function orderTs(order: IbkrOrder): number {
  const iso = order.filled_at ?? order.updated_at ?? order.submitted_at ?? null;
  const ms = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(ms) ? ms : 0;
}

/** The Time cell's own stamp as epoch ms; NaN (sorted last) when the order carries none. */
const orderStampMs = (order: IbkrOrder): number => Date.parse(order.filled_at ?? order.updated_at ?? order.submitted_at ?? '');

/** A Source cell's words, or null for its "—" (no stamp), so it sorts with the unknowns. */
const knownSource = (label: string): string | null => (label === '—' ? null : label);

const POSITION_COLUMNS: SortColumns<AccountPosition> = {
  symbol: (p) => p.symbol,
  qty: (p) => p.qty,
  avg: (p) => p.avgCost,
  last: (p) => p.mark,
  mkt_value: (p) => p.marketValue,
  unrealized: (p) => p.unrealized,
};

const FILL_COLUMNS: SortColumns<AccountFillRow> = {
  time: (f) => f.ts,
  symbol: (f) => f.symbol,
  side: (f) => f.side,
  qty: (f) => f.qty,
  price: (f) => f.price,
  comm: (f) => f.commission,
  fees: (f) => f.fees,
  source: (f) => knownSource(sourceLabel(f.source, f.botId)),
};

/** Orders sort on what each cell shows; the Source column reads the fills' stamps. */
function orderColumns(fillSource: ReadonlyMap<number, AccountFillRow>): SortColumns<IbkrOrder> {
  return {
    time: orderStampMs,
    symbol: (o) => o.symbol,
    side: (o) => o.side,
    qty: (o) => o.qty,
    type: (o) => o.order_type,
    price: orderPriceCell,
    status: orderStatusLabel,
    source: (o) => knownSource(orderSourceCell(o, fillSource.get(o.order_id)).label),
  };
}

export function PositionsOrdersPanel({ practice, venue, positions, working, closed, fills, today = null }: Props) {
  const [tab, setTab] = useState<PosTab>('orders');
  const [filter, setFilter] = useState<AccountOrderFilter>('all');
  // One row per order by identity, not order_id: ids repeat (C29).
  const orders = uniqueOrders([...working, ...closed]).sort((a, b) => orderTs(b) - orderTs(a));
  const orderKeys = orderRowKeys(orders);
  const fillSource = useMemo(() => new Map(fills.map((f) => [f.orderId, f] as const)), [fills]);
  const count = (bucket: AccountOrderFilter): number =>
    bucket === 'all' ? orders.length : orders.filter((o) => orderBucket(o) === bucket).length;
  const shown = filter === 'all' ? orders : orders.filter((o) => orderBucket(o) === filter);
  const newestFills = [...fills].sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));
  const held = positions.filter((p) => p.qty !== 0);
  const orderCols = useMemo(() => orderColumns(fillSource), [fillSource]);
  const positionSort = useTableSort('account.positions', held, POSITION_COLUMNS);
  const orderSort = useTableSort('account.orders', shown, orderCols);
  const fillSort = useTableSort('account.fills', newestFills, FILL_COLUMNS);
  const foot = !practice
    ? tab === 'fills' ? ACCOUNT_FILLS_FOOT_LIVE : ACCOUNT_POS_FOOT_LIVE
    : venue === 'sim' ? ACCOUNT_POS_FOOT_SIM : ACCOUNT_POS_FOOT;
  const tabs: Array<[PosTab, string, number]> = [
    ['positions', ACCOUNT_POS_TAB_POSITIONS, held.length],
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
            <thead>
              <tr>
                <SortTh col="symbol" sort={positionSort.sort} onSort={positionSort.onSort}>{ACCOUNT_COL_SYMBOL}</SortTh>
                <SortTh col="qty" sort={positionSort.sort} onSort={positionSort.onSort} className="r">{ACCOUNT_COL_QTY}</SortTh>
                <SortTh col="avg" sort={positionSort.sort} onSort={positionSort.onSort} className="r">{ACCOUNT_COL_AVG}</SortTh>
                <SortTh col="last" sort={positionSort.sort} onSort={positionSort.onSort} className="r">{ACCOUNT_COL_LAST}</SortTh>
                <SortTh col="mkt_value" sort={positionSort.sort} onSort={positionSort.onSort} className="r">{ACCOUNT_COL_MKT_VALUE}</SortTh>
                <SortTh col="unrealized" sort={positionSort.sort} onSort={positionSort.onSort} className="r">{ACCOUNT_COL_UNREALIZED}</SortTh>
              </tr>
            </thead>
            <tbody>
              {positionSort.rows.length === 0 ? (
                <tr><td colSpan={6} className="acct-muted">{ACCOUNT_POSITIONS_EMPTY}</td></tr>
              ) : positionSort.rows.map((p) => (
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
            <thead>
              <tr>
                <SortTh col="time" sort={orderSort.sort} onSort={orderSort.onSort}>{ACCOUNT_COL_TIME}</SortTh>
                <SortTh col="symbol" sort={orderSort.sort} onSort={orderSort.onSort}>{ACCOUNT_COL_SYMBOL}</SortTh>
                <SortTh col="side" sort={orderSort.sort} onSort={orderSort.onSort}>{ACCOUNT_COL_SIDE}</SortTh>
                <SortTh col="qty" sort={orderSort.sort} onSort={orderSort.onSort} className="r">{ACCOUNT_COL_QTY}</SortTh>
                <SortTh col="type" sort={orderSort.sort} onSort={orderSort.onSort}>{ACCOUNT_COL_TYPE}</SortTh>
                <SortTh col="price" sort={orderSort.sort} onSort={orderSort.onSort} className="r">{ACCOUNT_COL_PRICE}</SortTh>
                <SortTh col="status" sort={orderSort.sort} onSort={orderSort.onSort}>{ACCOUNT_COL_STATUS}</SortTh>
                <SortTh col="source" sort={orderSort.sort} onSort={orderSort.onSort}>{ACCOUNT_COL_SOURCE}</SortTh>
              </tr>
            </thead>
            <tbody>
              {orderSort.rows.length === 0 ? (
                <tr><td colSpan={8} className="acct-muted">{ACCOUNT_ORDERS_EMPTY}</td></tr>
              ) : orderSort.rows.map((o) => {
                const bucket = orderBucket(o);
                const src = orderSourceCell(o, fillSource.get(o.order_id));
                const price = orderPriceCell(o);
                return (
                  <tr key={orderKeys[orders.indexOf(o)]} data-testid={`account-order-${o.order_id}`} data-bucket={bucket}>
                    <td className="acct-num">{etOrderStamp(o.filled_at ?? o.updated_at ?? o.submitted_at, today)}</td>
                    <td>{o.symbol}</td>
                    <td className={o.side === 'BUY' ? 'acct-side--buy' : 'acct-side--sell'}>{o.side}</td>
                    <td className="r acct-num">{formatShareQty(o.qty)}</td>
                    <td>{o.order_type}</td>
                    <td
                      className={`r acct-num${bucket === 'canceled' || bucket === 'expired' || price == null ? ' acct-muted' : ''}`}
                      title={price == null ? ACCOUNT_PRICE_NONE_TITLE : undefined}
                    >
                      {price == null ? ACCOUNT_PRICE_NONE : price.toFixed(2)}{bucket === 'filled' && price != null && (o.fill_estimated || practice) && <EstChip />}
                    </td>
                    <td className={bucket === 'filled' || bucket === 'working' ? '' : 'acct-muted'}>{orderStatusLabel(o)}</td>
                    <td className={`acct-src${src.bot ? ' is-bot' : ''}`} data-testid={`account-order-source-${o.order_id}`}>
                      {src.label}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {tab === 'fills' && (
          <table className="acct-table" data-testid="account-fills-table">
            <thead>
              <tr>
                <SortTh col="time" sort={fillSort.sort} onSort={fillSort.onSort}>{ACCOUNT_COL_TIME}</SortTh>
                <SortTh col="symbol" sort={fillSort.sort} onSort={fillSort.onSort}>{ACCOUNT_COL_SYMBOL}</SortTh>
                <SortTh col="side" sort={fillSort.sort} onSort={fillSort.onSort}>{ACCOUNT_COL_SIDE}</SortTh>
                <SortTh col="qty" sort={fillSort.sort} onSort={fillSort.onSort} className="r">{ACCOUNT_COL_QTY}</SortTh>
                <SortTh col="price" sort={fillSort.sort} onSort={fillSort.onSort} className="r">{ACCOUNT_COL_PRICE}</SortTh>
                <SortTh col="comm" sort={fillSort.sort} onSort={fillSort.onSort} className="r">{ACCOUNT_COL_COMM}</SortTh>
                <SortTh col="fees" sort={fillSort.sort} onSort={fillSort.onSort} className="r">{ACCOUNT_COL_FEES}</SortTh>
                <SortTh col="source" sort={fillSort.sort} onSort={fillSort.onSort}>{ACCOUNT_COL_SOURCE}</SortTh>
              </tr>
            </thead>
            <tbody>
              {fillSort.rows.length === 0 ? (
                <tr><td colSpan={8} className="acct-muted">{ACCOUNT_FILLS_EMPTY}</td></tr>
              ) : fillSort.rows.map((f) => (
                <tr key={f.key} data-testid={`account-fill-${f.orderId}`}>
                  <td className="acct-num">{etTime(f.ts)}</td>
                  <td>{f.symbol}</td>
                  <td className={f.side === 'BUY' ? 'acct-side--buy' : 'acct-side--sell'}>{f.side}</td>
                  <td className="r acct-num">{formatShareQty(f.qty)}</td>
                  <td className="r acct-num">{f.price.toFixed(2)}{f.estimated && <EstChip />}</td>
                  <td className="r acct-num">{formatMoney(f.commission)}</td>
                  <td className="r acct-num">{formatMoney(f.fees)}</td>
                  <td className={`acct-src${sourceKind(f.source) === 'bot' || f.botId ? ' is-bot' : ''}`}>{sourceLabel(f.source, f.botId)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="acct-foot">{foot}</p>
    </section>
  );
}
