/**
 * Account (frozen mockup R2-Account): what the account is worth, today's result, both books, the
 * loss limit, and positions, working orders and fills. The figures are the desk's Account page
 * figures (`usePhoneAccount`); the curve is the desk's own curve geometry over today's ledger.
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { dayShortLabel } from '../../account/accountCalendar';
import { rangeNetPnl } from '../../account/accountFigures';
import type { AccountPosition } from '../../account/accountPositions';
import type { AccountFillRow } from '../../account/accountLive';
import { lineGeometry, rangeSeries, type Frame } from '../../account/equityPath';
import { ALL_VIEW, type OwnerView } from '../../account/ownerView';
import { ACCOUNT_HISTORY_RANGES, type AccountRange } from '../../constantGroups/account_page';
import { OWNER_BOOK_BOTS, OWNER_BOOK_YOU } from '../../constantGroups/owners';
import { formatOrderType } from '../../ibkr/orderDisplay';
import type { IbkrOrder } from '../../ibkr/types';
import { formatMoney } from '../../utils/formatMoney';
import { LinkPill, PadlockButton, PhoneScreen, RowLink, TickerChip, VenuePill } from '../PhoneChrome';
import { daySeries } from '../phoneCalendar';
import { px, shares, signedMoney, toneClass, toneOf } from '../phoneFormat';
import { usePhoneSession } from '../PhoneSession';
import { usePhoneAccount, type PhoneAccount } from '../usePhoneAccount';
import { usePhoneLossLimit } from '../usePhoneLossLimit';
import { useRowsThatFit } from '../useRowsThatFit';
import { AccountCalendar } from './AccountCalendar';
import './account.css';

type Book = 'all' | 'you' | 'bots';
type ListTab = 'positions' | 'orders' | 'fills';
type Mode = 'overview' | 'calendar';
const MODES: readonly { id: Mode; name: string }[] = [{ id: 'overview', name: 'Overview' }, { id: 'calendar', name: 'Calendar' }];

const BOOKS: readonly { id: Book; name: string; view: OwnerView }[] = [
  { id: 'all', name: 'All', view: ALL_VIEW },
  { id: 'you', name: 'You', view: { book: 'you', bot: null } },
  { id: 'bots', name: 'Bots', view: { book: 'bots', bot: null } },
];
const ONE_BOOK = 'Only Paper keeps your book and the bots\' book apart.';
const ROW_PX = 42;
const CURVE: Frame = { width: 336, height: 64, padLeft: 0, padRight: 0, padTop: 6, padBottom: 4 };
const ET_HM = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false });

/** What the chart covers: one of the desk's ranges, or one past day opened from the calendar. */
type Span = { range: AccountRange } | { day: string };

function Curve({ account, book, span, net }: { account: PhoneAccount; book: Book; span: Span; net: number | null }) {
  const day = 'day' in span ? span.day : null;
  const geo = useMemo(() => {
    if (day) {
      const series = account.calendar ? daySeries(account.calendar, day) : [];
      return series.length > 1 ? lineGeometry(series, CURVE, 0) : null;
    }
    if (!account.rangeHistory) return null;
    // The whole account is drawn as its value; one book as its own P&L, from zero.
    const { series, baseline } = rangeSeries(
      account.rangeHistory,
      book === 'all' ? 'value' : 'pnl',
      { openPnl: account.openPnl, netLiquidation: account.figures.netLiquidation },
      account.nowTs,
    );
    return series.length > 1 ? lineGeometry(series, CURVE, baseline, account.nowTs) : null;
  }, [day, account.calendar, account.rangeHistory, account.openPnl, account.figures.netLiquidation, account.nowTs, book]);
  const tone = toneOf(net) === 'bad' ? 'bad' : 'good';
  if (!geo) {
    const reading = day ? account.calendar : account.rangeHistory;
    return (
      <div className="ph-acct__curve is-empty" role="status">
        {account.venue === 'live' ? 'IBKR sends no curve.' : reading ? 'No fills to draw here.' : 'Reading the ledger…'}
      </div>
    );
  }
  return (
    <div className="ph-acct__curve" data-tone={tone}>
      <svg viewBox={`0 0 ${CURVE.width} ${CURVE.height}`} preserveAspectRatio="none" role="img"
        aria-label={day ? `P&L on ${dayShortLabel(day)}` : book === 'all' ? 'Account value over the range' : 'P&L of this book over the range'}>
        <path className="ph-acct__curve-area" d={geo.area} />
        {geo.baselineY != null ? <line className="ph-acct__curve-base" x1={0} x2={CURVE.width} y1={geo.baselineY} y2={geo.baselineY} /> : null}
        <path className="ph-acct__curve-line" d={geo.line} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function who(owner: 'you' | 'bots' | null | undefined) {
  return <span className="ph-who" data-owner={owner ?? 'you'}>{owner === 'bots' ? 'Bot' : 'You'}</span>;
}

function PositionRow({ p, split }: { p: AccountPosition; split: boolean }) {
  return (
    <div className="ph-acct__row is-position" data-testid={`phone-position-${p.symbol}`}>
      <span><TickerChip symbol={p.symbol} /></span>
      {split ? who(p.owner) : <span />}
      <b>{p.qty < 0 ? '-' : ''}{shares(p.qty)}</b>
      <span className="ph-muted">{px(p.avgCost)}</span>
      <span>{px(p.mark)}</span>
      <b className={toneClass(p.unrealized)}>{signedMoney(p.unrealized)}</b>
      <RowLink symbol={p.symbol} />
    </div>
  );
}

function orderPrice(o: IbkrOrder): string {
  const price = o.limit_price ?? o.stop_price ?? null;
  return price != null ? px(price) : formatOrderType(o.order_type);
}

function OrderRow({ o, split }: { o: IbkrOrder; split: boolean }) {
  const { send } = usePhoneSession();
  const words = `${o.symbol} ${o.side === 'BUY' ? 'Buy' : 'Sell'} ${shares(o.remaining_qty ?? o.qty)}`;
  return (
    <div className="ph-acct__row is-order" data-testid={`phone-order-${o.order_id}`}>
      <span><TickerChip symbol={o.symbol} /></span>
      {split ? who(o.owner) : <span />}
      <b className={o.side === 'BUY' ? 'ph-good' : 'ph-bad'}>{o.side === 'BUY' ? 'Buy' : 'Sell'} {shares(o.remaining_qty ?? o.qty)}</b>
      <span>{orderPrice(o)}</span>
      <span className="ph-acct__act">
        <button type="button" className="ph-pill-btn is-danger" onClick={() => send(`Cancel ${words}`, (door) => door.cancelOrder(o.order_id, words))}>
          Cancel
        </button>
      </span>
      <RowLink symbol={o.symbol} />
    </div>
  );
}

function FillRow({ f }: { f: AccountFillRow }) {
  return (
    <div className="ph-acct__row is-fill">
      <span><TickerChip symbol={f.symbol} /></span>
      <b className={f.side === 'BUY' ? 'ph-good' : 'ph-bad'}>{f.side === 'BUY' ? 'Buy' : 'Sell'} {shares(f.qty)}</b>
      <span>{px(f.price)}</span>
      <span className="ph-muted">{f.ts != null ? ET_HM.format(new Date(f.ts * 1000)) : '—'}</span>
      <RowLink symbol={f.symbol} />
    </div>
  );
}

const HEADS: Record<ListTab, readonly string[]> = {
  positions: ['Symbol', '', 'Qty', 'Avg', 'Last', 'Open P&L'],
  orders: ['Symbol', '', 'Order', 'Price', ''],
  fills: ['Symbol', 'Fill', 'Price', 'Time ET'],
};
const EMPTY: Record<ListTab, string> = {
  positions: 'No open positions.',
  orders: 'No working orders.',
  fills: 'No fills today.',
};

const RANGE_NAMES: Record<AccountRange, string> = { '1D': '1D', '5D': '5D', '1M': '1M', '3M': '3M', YTD: 'YTD', ALL: 'All' };

export function AccountScreen() {
  const [book, setBook] = useState<Book>('all');
  const [mode, setMode] = useState<Mode>('overview');
  const [span, setSpan] = useState<Span>({ range: '1D' });
  const [tab, setTab] = useState<ListTab>('positions');
  const [page, setPage] = useState(0);
  const day = 'day' in span ? span.day : null;
  const range = 'range' in span ? span.range : '1D';
  const account = usePhoneAccount(BOOKS.find((b) => b.id === book)?.view ?? ALL_VIEW, { range, calendar: mode === 'calendar' || day != null });
  const limit = usePhoneLossLimit(account.venue);
  const listRef = useRef<HTMLDivElement>(null);
  const fit = useRowsThatFit(listRef, ROW_PX);
  const split = account.books != null;
  // Off Paper there is one book: the switch falls back to All and says why.
  const shownBook: Book = split ? book : 'all';

  const counts: Record<ListTab, number> = {
    positions: account.positions.length, orders: account.working.length, fills: account.fills.length,
  };
  const total = counts[tab];
  // When the rows do not all fit, the last line becomes the pager.
  const perPage = total > fit ? Math.max(1, fit - 1) : fit;
  const pages = Math.max(1, Math.ceil(total / perPage));
  const at = Math.min(page, pages - 1);
  useLayoutEffect(() => {
    if (at !== page) setPage(at);
  }, [at, page]);
  const from = at * perPage;

  const f = account.figures;
  const stats: readonly { name: string; value: string; tone: string }[] = [
    { name: 'Open P&L', value: signedMoney(account.openPnl), tone: toneClass(account.openPnl) },
    { name: 'Realized today', value: signedMoney(account.realizedToday), tone: toneClass(account.realizedToday) },
    { name: 'Buying power', value: formatMoney(f.buyingPower, 0), tone: '' },
    { name: 'Commissions today', value: formatMoney(account.commissionsToday), tone: '' },
    { name: `${OWNER_BOOK_YOU} · today`, value: split ? signedMoney(account.books?.you.day_pnl) : '—', tone: split ? toneClass(account.books?.you.day_pnl) : '' },
    { name: `${OWNER_BOOK_BOTS} · today`, value: split ? signedMoney(account.books?.bots.day_pnl) : '—', tone: split ? toneClass(account.books?.bots.day_pnl) : '' },
  ];
  const usedShare = limit.used != null && limit.limit ? Math.min(1, limit.used / limit.limit) : 0;
  // The figure beside the chart is the chart's: the day opened from the calendar, the range, or today.
  const dayNet = day && account.calendar ? account.calendar.daily.filter((d) => d.date === day).reduce((s, d) => s + d.realized, 0) : null;
  const net = day ? dayNet
    : range === '1D' ? account.dayPnl
    : account.rangeHistory ? rangeNetPnl(account.rangeHistory.components, account.openPnl) : null;
  const whose = shownBook === 'all' ? '' : shownBook === 'you' ? 'You, ' : 'Bots, ';
  const netName = day ? `${whose}${dayShortLabel(day)}`
    : range === '1D' ? (shownBook === 'all' ? 'Today, net' : `${whose}today`)
    : `${whose}${RANGE_NAMES[range]}${shownBook === 'all' ? ', net' : ''}`;

  return (
    <PhoneScreen
      name="account"
      tab="account"
      header={(
        <div className="ph-head">
          <VenuePill />
          <div className="ph-head__title">Account</div>
          <div className="ph-grow" />
          <LinkPill live />
          <PadlockButton />
        </div>
      )}
    >
      <div className="ph-acct__switches">
        <div className="ph-seg ph-acct__books" role="group" aria-label="Which view">
          {MODES.map((m) => (
            <button key={m.id} type="button" aria-pressed={m.id === mode} data-testid={`phone-account-${m.id}`} onClick={() => setMode(m.id)}>{m.name}</button>
          ))}
        </div>
        <div className="ph-seg ph-acct__books" role="group" aria-label="Whose book">
          {BOOKS.map((b) => (
            <button
              key={b.id}
              type="button"
              aria-pressed={b.id === shownBook}
              disabled={!split && b.id !== 'all'}
              data-why={!split && b.id !== 'all' ? ONE_BOOK : undefined}
              onClick={() => { setBook(b.id); setPage(0); }}
            >
              {b.name}
            </button>
          ))}
        </div>
      </div>
      {mode === 'calendar' ? (
        <AccountCalendar account={account} onChart={(date) => { setSpan({ day: date }); setMode('overview'); }} />
      ) : (
      <>
      <div className="ph-acct__top">
        <div className="ph-card ph-acct__value" data-tone={toneOf(net) || 'flat'} data-testid="phone-account-value">
          <div className="ph-acct__value-top">
            <div>
              <div className="ph-label">Total account value</div>
              <div className="ph-acct__tav">{formatMoney(f.netLiquidation)}</div>
            </div>
            <div className="ph-acct__net">
              <div className="ph-label" data-testid="phone-account-net-name">{netName}</div>
              <div className={`ph-acct__netpill ${toneClass(net)}`}>{signedMoney(net)}</div>
            </div>
          </div>
          <Curve account={account} book={shownBook} span={span} net={net} />
          <div className="ph-acct__ranges" role="group" aria-label="What the chart covers">
            {day ? (
              <button type="button" aria-pressed data-testid="phone-account-day" onClick={() => setSpan({ range: '1D' })}>
                {dayShortLabel(day).split(', ')[1]} <X size={11} aria-hidden />
              </button>
            ) : null}
            {ACCOUNT_HISTORY_RANGES.map((r) => (
              <button key={r} type="button" aria-pressed={!day && r === range} data-testid={`phone-account-range-${r}`} onClick={() => setSpan({ range: r })}>
                {RANGE_NAMES[r]}
              </button>
            ))}
          </div>
        </div>

        <div className="ph-card ph-acct__stats">
          {stats.map((s) => (
            <div key={s.name}>
              <i>{s.name}</i>
              <b className={s.tone}>{s.value}</b>
            </div>
          ))}
        </div>

        <div className="ph-card ph-acct__limit" data-testid="phone-loss-limit">
          <div>
            <span className="ph-muted">Daily loss limit</span>
            <span>
              {limit.error && limit.used == null
                ? <span className="ph-muted">not counted</span>
                : <><b>{formatMoney(limit.used, 0)}</b> <span className="ph-muted">of {formatMoney(limit.limit, 0)} used</span></>}
            </span>
          </div>
          <div className="ph-acct__bar" data-state={limit.stopped ? 'stopped' : limit.warned ? 'warned' : 'ok'}>
            <i style={{ width: `${Math.max(2, usedShare * 100).toFixed(0)}%` }} />
          </div>
        </div>
      </div>

      <div className="ph-undertabs ph-acct__tabs">
        {(['positions', 'orders', 'fills'] as const).map((t) => (
          <button key={t} type="button" aria-pressed={t === tab} onClick={() => { setTab(t); setPage(0); }}>
            {t[0].toUpperCase() + t.slice(1)} · {counts[t]}
          </button>
        ))}
      </div>
      {account.error ? (
        // The rows under this are the last ones read: the reason takes the column heads' line, so nothing moves.
        <div className="ph-acct__stale" role="alert" data-testid="phone-account-error">{account.error}</div>
      ) : (
        <div className={`ph-acct__head is-${tab}`}>
          {HEADS[tab].map((h, i) => <div key={`${h}-${i}`}>{h}</div>)}
        </div>
      )}
      <div className="ph-acct__list" ref={listRef} data-testid="phone-account-list">
        {!total ? <div className="ph-empty" role="status">{account.error ? 'Nothing was read.' : EMPTY[tab]}</div> : null}
        {tab === 'positions' ? account.positions.slice(from, from + perPage).map((p) => (
          <PositionRow key={`${p.symbol}-${p.owner ?? ''}-${p.bot ?? ''}`} p={p} split={split} />
        )) : null}
        {tab === 'orders' ? account.working.slice(from, from + perPage).map((o) => <OrderRow key={o.order_id} o={o} split={split} />) : null}
        {tab === 'fills' ? account.fills.slice(from, from + perPage).map((row) => <FillRow key={row.key} f={row} />) : null}
        {pages > 1 ? (
          <div className="ph-acct__pager">
            <span>{from + 1} to {Math.min(total, from + perPage)} of {total}</span>
            <span>
              <button type="button" className="ph-pill-btn" disabled={at === 0} data-why="This is the first page." onClick={() => setPage(at - 1)}>‹ Prev</button>
              <button type="button" className="ph-pill-btn" disabled={at >= pages - 1} data-why="This is the last page." onClick={() => setPage(at + 1)}>Next ›</button>
            </span>
          </div>
        ) : null}
      </div>
      </>
      )}
    </PhoneScreen>
  );
}
