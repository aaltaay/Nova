/**
 * One practice day, opened from the Calendar (operator ask, 2026-10-26): where
 * the day's money went -- gross, less commissions, less SEC + FINRA fees,
 * equals net -- then the day's trades, shares and bot share, every stock it
 * touched, and every trade from flat back to flat. It takes the Ledger's place
 * while it is open, so the Calendar and the Fills tab (which follows the day)
 * stay in view; closing it brings the Ledger back. The page keys it by its
 * date, so another day opens with the short trade list.
 */
import { useEffect, useRef, useState } from 'react';
import {
  ACCOUNT_COMP_COMMISSIONS,
  ACCOUNT_COMP_FEES,
  ACCOUNT_DAY_ARCHIVED_NOTE,
  ACCOUNT_DAY_BOT,
  ACCOUNT_DAY_BY_STOCK,
  ACCOUNT_DAY_CLOSE,
  ACCOUNT_DAY_COL_AVG,
  ACCOUNT_DAY_COL_BY,
  ACCOUNT_DAY_COL_COMM,
  ACCOUNT_DAY_COL_NET,
  ACCOUNT_DAY_COL_SHARES,
  ACCOUNT_DAY_COL_SIDE,
  ACCOUNT_DAY_COL_STOCK,
  ACCOUNT_DAY_COL_TIME,
  ACCOUNT_DAY_COL_TRADES,
  ACCOUNT_DAY_GROSS,
  ACCOUNT_DAY_LONG,
  ACCOUNT_DAY_NET,
  ACCOUNT_DAY_NO_TRADES,
  ACCOUNT_DAY_PANEL_TITLE,
  ACCOUNT_DAY_PARTIAL_NOTE,
  ACCOUNT_DAY_SHARES,
  ACCOUNT_DAY_SHORT,
  ACCOUNT_DAY_SHOW_FEWER,
  ACCOUNT_DAY_TILE_BOT_SUB,
  ACCOUNT_DAY_TRADES,
  ACCOUNT_DAY_TRADES_HEAD,
  ACCOUNT_DAY_TRADES_SHOWN,
  ACCOUNT_DAY_WHERE,
  ACCOUNT_SOURCE_BOT,
  ACCOUNT_SOURCE_MANUAL,
  ACCOUNT_TRADE_DEFINITION,
  accountDayPerTrade,
  accountDayShowAll,
  accountDayShowFills,
  accountDaySummary,
  accountDayTileSharesSub,
  accountDayWonLost,
} from '../constantGroups/account_page';
import { TickerLink } from '../components/TickerLink';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { Money, PanelHead, etTime, toneOf, type Tone } from './accountBits';
import { dayLongLabel } from './accountCalendar';
import type { DayBreakdown, DayStock } from './accountDayBreakdown';

interface Props {
  day: DayBreakdown;
  onClose: () => void;
  /** Turn the Fills tab to this day's fills and bring it into view. */
  onShowFills: () => void;
}

/** A bar's fill class: up / down past the P&L floor, muted for a cost or a small move. */
const barTone = (tone: Tone): string => `acct-day-bar__fill--${tone === 'up' || tone === 'down' ? tone : 'muted'}`;

interface Step {
  key: string;
  label: string;
  from: number;
  to: number;
  value: number;
  cost: boolean;
}

/** Gross, less commissions, less fees, equals net -- each a bar on one scale through zero. */
export function waterfallSteps(day: Pick<DayBreakdown, 'gross' | 'commissions' | 'fees' | 'net'>): Step[] {
  const afterComm = day.gross - day.commissions;
  return [
    { key: 'gross', label: ACCOUNT_DAY_GROSS, from: 0, to: day.gross, value: day.gross, cost: false },
    { key: 'commissions', label: ACCOUNT_COMP_COMMISSIONS, from: day.gross, to: afterComm, value: -day.commissions, cost: true },
    { key: 'fees', label: ACCOUNT_COMP_FEES, from: afterComm, to: day.net, value: -day.fees, cost: true },
    { key: 'net', label: ACCOUNT_DAY_NET, from: 0, to: day.net, value: day.net, cost: false },
  ];
}

function Waterfall({ day }: { day: DayBreakdown }) {
  const steps = waterfallSteps(day);
  const ends = steps.flatMap((s) => [s.from, s.to]);
  const lo = Math.min(0, ...ends);
  const hi = Math.max(0, ...ends);
  const span = hi - lo || 1;
  const pct = (v: number): string => `${((v - lo) / span) * 100}%`;
  return (
    <div className="acct-day-wf" data-testid="account-day-waterfall">
      {steps.map((s) => (
        <div key={s.key} className="acct-day-wf__row" data-testid={`account-day-step-${s.key}`}>
          <span className="acct-muted">{s.label}</span>
          <div className="acct-day-bar">
            <i className="acct-day-bar__zero" style={{ left: pct(0) }} />
            <i
              className={`acct-day-bar__fill ${barTone(s.cost ? 'muted' : toneOf(s.value))}`}
              style={{ left: pct(Math.min(s.from, s.to)), width: `max(2px, ${(Math.abs(s.to - s.from) / span) * 100}%)` }}
            />
          </div>
          <span className="acct-day-wf__v"><Money value={s.value} signed kind={s.cost ? 'cost' : 'pnl'} /></span>
        </div>
      ))}
    </div>
  );
}

function Tile({ k, v, sub, title }: { k: string; v: string; sub: string; title?: string }) {
  return (
    <div className="acct-card" title={title}>
      <div className="acct-muted acct-day-tile__k">{k}</div>
      <div className="acct-card__v acct-num">{v}</div>
      <div className="acct-muted acct-day-tile__s">{sub}</div>
    </div>
  );
}

/** A stock's net as a bar from the middle: left for a loss, right for a gain. */
function NetBar({ stock, widest }: { stock: DayStock; widest: number }) {
  const half = (Math.abs(stock.net) / (widest || 1)) * 50;
  const tone = toneOf(stock.net);
  return (
    <div className="acct-day-bar acct-day-bar--mid">
      <i className="acct-day-bar__zero" style={{ left: '50%' }} />
      <i className={`acct-day-bar__fill ${barTone(tone)}`} style={stock.net < 0 ? { right: '50%', width: `${half}%` } : { left: '50%', width: `${half}%` }} />
    </div>
  );
}

const price = (n: number | null): string => (n == null ? '—' : n.toFixed(2));
const hhmm = (ts: number): string => etTime(ts).slice(0, 5);

export function DayBreakdownPanel({ day, onClose, onShowFills }: Props) {
  const ref = useRef<HTMLElement>(null);
  const [allTrades, setAllTrades] = useState(false);
  // An opened day comes into view where the panels stack (a 1280 or 1440 window).
  useEffect(() => {
    ref.current?.scrollIntoView?.({ block: 'nearest' });
  }, []);
  const widest = Math.max(0, ...day.stocks.map((s) => Math.abs(s.net)));
  const trades = allTrades ? day.trades : day.trades.slice(0, ACCOUNT_DAY_TRADES_SHOWN);
  const perTrade = day.trades.length > 0 ? accountDayPerTrade(formatMoney(day.commissions / day.trades.length)) : '—';

  return (
    <section ref={ref} className="acct-panel acct-panel--ledger acct-panel--day" data-testid="account-day" aria-label={ACCOUNT_DAY_PANEL_TITLE}>
      <PanelHead title={ACCOUNT_DAY_PANEL_TITLE}>
        <button type="button" className="acct-day__close" aria-label={ACCOUNT_DAY_CLOSE} title={ACCOUNT_DAY_CLOSE} data-testid="account-day-close" onClick={onClose}>×</button>
      </PanelHead>
      <div className="acct-day__top">
        <div>
          <div className="acct-day__date" data-testid="account-day-date">{dayLongLabel(day.date)}</div>
          <div className="acct-muted acct-day__sum">{accountDaySummary(day.trades.length, day.fills, day.stocks.length)}</div>
        </div>
        <span className="acct-day__net" data-testid="account-day-net"><Money value={day.net} signed /></span>
      </div>
      {!day.detailed && <p className="acct-hint">{ACCOUNT_DAY_ARCHIVED_NOTE}</p>}
      {day.partial && <p className="acct-hint">{ACCOUNT_DAY_PARTIAL_NOTE}</p>}

      <div className="acct-day__label">{ACCOUNT_DAY_WHERE}</div>
      <Waterfall day={day} />

      {day.detailed && (
        <>
          <div className="acct-day__tiles">
            <Tile k={ACCOUNT_DAY_TRADES} v={String(day.trades.length)} sub={accountDayWonLost(day.won, day.lost)} title={ACCOUNT_TRADE_DEFINITION} />
            <Tile k={ACCOUNT_DAY_SHARES} v={formatShareQty(day.sharesBought)} sub={accountDayTileSharesSub(formatShareQty(day.sharesSold))} />
            <Tile k={ACCOUNT_COMP_COMMISSIONS} v={formatMoney(day.commissions)} sub={perTrade} />
            <Tile k={ACCOUNT_DAY_BOT} v={`${day.botFills} / ${day.listedFills}`} sub={ACCOUNT_DAY_TILE_BOT_SUB} />
          </div>

          <div className="acct-day__label">{ACCOUNT_DAY_BY_STOCK}</div>
          <table className="acct-table" data-testid="account-day-stocks">
            <thead>
              <tr>
                <th>{ACCOUNT_DAY_COL_STOCK}</th>
                <th className="r">{ACCOUNT_DAY_COL_TRADES}</th>
                <th className="r">{ACCOUNT_DAY_COL_SHARES}</th>
                <th className="r">{ACCOUNT_DAY_COL_AVG}</th>
                <th className="r">{ACCOUNT_DAY_COL_COMM}</th>
                <th className="r">{ACCOUNT_DAY_COL_NET}</th>
                <th className="acct-day__barcol" />
              </tr>
            </thead>
            <tbody>
              {day.stocks.map((s) => (
                <tr key={s.symbol} data-testid={`account-day-stock-${s.symbol}`}>
                  <td><TickerLink symbol={s.symbol} /></td>
                  <td className="r acct-num">{s.trades}</td>
                  <td className="r acct-num">{formatShareQty(Math.max(s.bought, s.sold))}</td>
                  <td className="r acct-num">{price(s.avgBuy)} → {price(s.avgSell)}</td>
                  <td className="r"><Money value={-s.commission} signed kind="cost" /></td>
                  <td className="r"><Money value={s.net} signed /></td>
                  <td className="acct-day__barcol"><NetBar stock={s} widest={widest} /></td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="acct-day__label" title={ACCOUNT_TRADE_DEFINITION}>{ACCOUNT_DAY_TRADES_HEAD}</div>
          {day.trades.length === 0 ? (
            <p className="acct-hint">{ACCOUNT_DAY_NO_TRADES}</p>
          ) : (
            <table className="acct-table" data-testid="account-day-trades">
              <thead>
                <tr>
                  <th>{ACCOUNT_DAY_COL_TIME}</th>
                  <th>{ACCOUNT_DAY_COL_STOCK}</th>
                  <th>{ACCOUNT_DAY_COL_SIDE}</th>
                  <th className="r">{ACCOUNT_DAY_COL_SHARES}</th>
                  <th>{ACCOUNT_DAY_COL_BY}</th>
                  <th className="r">{ACCOUNT_DAY_COL_COMM}</th>
                  <th className="r">{ACCOUNT_DAY_COL_NET}</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={`${t.symbol}-${t.openTs}-${t.closeTs}`} data-testid="account-day-trade">
                    <td className="acct-num">{hhmm(t.openTs)}–{hhmm(t.closeTs)}</td>
                    <td><TickerLink symbol={t.symbol} /></td>
                    <td className={t.side === 'long' ? 'acct-side--buy' : 'acct-side--sell'}>{t.side === 'long' ? ACCOUNT_DAY_LONG : ACCOUNT_DAY_SHORT}</td>
                    <td className="r acct-num">{formatShareQty(t.shares)}</td>
                    <td className={`acct-src${t.bot ? ' is-bot' : ''}`}>{t.bot ? ACCOUNT_SOURCE_BOT : ACCOUNT_SOURCE_MANUAL}</td>
                    <td className="r"><Money value={-t.commission} signed kind="cost" /></td>
                    <td className="r"><Money value={t.net} signed /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {day.trades.length > ACCOUNT_DAY_TRADES_SHOWN && (
            <button type="button" className="acct-day__more" data-testid="account-day-more" onClick={() => setAllTrades((v) => !v)}>
              {allTrades ? ACCOUNT_DAY_SHOW_FEWER : accountDayShowAll(day.trades.length)}
            </button>
          )}
        </>
      )}

      {day.listedFills > 0 && (
        <div className="acct-day__foot">
          <button type="button" className="acct-day__fills" data-testid="account-day-show-fills" onClick={onShowFills}>
            {accountDayShowFills(day.listedFills)} ↓
          </button>
        </div>
      )}
    </section>
  );
}
