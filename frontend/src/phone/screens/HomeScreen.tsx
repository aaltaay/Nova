/**
 * Home (frozen mockup R2-Home): the day in one look. Today's P&L and the loss limit, the desk's
 * small-cap day read with its six checks (ADR 053), the top of the Gainers board, and what you hold
 * and what is working. Every figure is the desk's own; a list longer than its box ends in a line
 * that leads to the screen holding the rest.
 */
import { useEffect, useRef, useState } from 'react';
import { Settings } from 'lucide-react';
import type { AccountPosition } from '../../account/accountPositions';
import { whoName } from '../../account/ownerView';
import { sessionChipView } from '../../components/globalBarSession';
import { formatMoney } from '../../utils/formatMoney';
import { formatOrderType } from '../../ibkr/orderDisplay';
import type { IbkrOrder } from '../../ibkr/types';
import { MARKET_OFF, MARKET_OLD_API, TEMP_WORD } from '../../market_board/constants';
import { DEFAULT_PERIODS } from '../../market_board/periods';
import type { Check, DayRead, Session } from '../../market_board/types';
import { useMarketBoard } from '../../market_board/useMarketBoard';
import { useLiveScannerFeed } from '../../scanner/ScannerDataContext';
import { useSettings } from '../../settings';
import type { ScannerRow } from '../../types/scanner';
import { LinkPill, PadlockButton, PhoneScreen, RowLink, TickerChip, VenuePill } from '../PhoneChrome';
import { catalystLine } from '../phoneCatalyst';
import { pct1, px, shares, signedMoney, toneClass } from '../phoneFormat';
import { go } from '../phoneRoute';
import { usePhoneSession } from '../PhoneSession';
import { usePhoneAccount } from '../usePhoneAccount';
import { usePhoneCatalyst } from '../usePhoneCatalyst';
import { usePhoneLossLimit } from '../usePhoneLossLimit';
import { useRowsThatFit } from '../useRowsThatFit';
import './home.css';

const RUNNERS = 5;
const HOLD_ROW_PX = 33;
const CHECK_ICON: Record<Check['state'], string> = { green: '✓', amber: '!', red: '✕', waiting: '–', unknown: '?' };
const PHASE_WORD: Record<Session['phase'], string> = {
  premarket: 'pre', regular: 'open', after_hours: 'after', closed: 'closed',
};
const CHIP_WORD = { premarket: 'pre', open: 'open', afterhours: 'after', closed: 'closed' } as const;
const VERDICT: Record<NonNullable<DayRead['verdict']>, string> = { bullish: 'Bullish', mixed: 'Mixed', bearish: 'Bearish' };
const SPANS = ['day', 'week', 'month'] as const;
const ET_HM = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false });

function useMinuteClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 10_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

/** "09:31 ET · open". The phase is the market board's (it knows a holiday); the desk's clock chip until it loads. */
function sessionLine(now: Date, session: Session | null): string {
  const phase = session ? PHASE_WORD[session.phase] : CHIP_WORD[sessionChipView(now).kind];
  return `${ET_HM.format(now)} ET · ${phase}`;
}

function ScoreRing({ read }: { read: DayRead }) {
  const r = 23;
  const around = 2 * Math.PI * r;
  const share = read.total > 0 ? read.green / read.total : 0;
  return (
    <svg className="ph-home__ring" data-verdict={read.verdict ?? 'none'} width="56" height="56" viewBox="0 0 56 56"
      role="img" aria-label={`${read.green} of ${read.total} checks green`}>
      <circle cx="28" cy="28" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="5" />
      {share > 0 ? (
        <circle cx="28" cy="28" r={r} fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${(around * share).toFixed(1)} ${around.toFixed(1)}`} transform="rotate(-90 28 28)" />
      ) : null}
      <text x="28" y="27" textAnchor="middle" fontSize="15" fontWeight="700">{read.green}/{read.total}</text>
      <text x="28" y="38" textAnchor="middle" fontSize="8" fontWeight="600" className="ph-home__ring-label">CHECKS</text>
    </svg>
  );
}

function DayReadCard() {
  const board = useMarketBoard(DEFAULT_PERIODS);
  const data = board.data;
  if (!data) {
    const words = board.unavailable ? MARKET_OLD_API : board.error ?? 'Reading the market…';
    return <div className="ph-card ph-home__read is-empty" role="status">{words}</div>;
  }
  if (!data.enabled) return <div className="ph-card ph-home__read is-empty" role="status">{MARKET_OFF}</div>;
  const read = data.day_read;
  const t = read.temperature;
  return (
    <div className="ph-card ph-home__read" data-verdict={read.verdict ?? 'none'} data-testid="phone-day-read">
      <div className="ph-home__read-top">
        <div className="ph-home__read-words">
          <div className="ph-label">Small caps today</div>
          <div className="ph-home__verdict">{read.verdict ? VERDICT[read.verdict] : 'No read yet'}</div>
          <div className="ph-home__temp">
            {t ? SPANS.map((span, i) => {
              const label = t[span];
              return (
                <span key={span}>
                  {i ? ' · ' : ''}
                  <b data-temp={label ?? 'none'}>{label ? `${i ? TEMP_WORD[label].toLowerCase() : TEMP_WORD[label][0] + TEMP_WORD[label].slice(1).toLowerCase()} ${span}` : `-- ${span}`}</b>
                </span>
              );
            }) : (read.verdict ? '' : `${read.known} of ${read.total} checks have data`)}
          </div>
        </div>
        <ScoreRing read={read} />
      </div>
      <div className="ph-home__checks">
        {read.checks.map((c) => (
          <div key={c.id} className="ph-home__check" data-state={c.state}>
            <i aria-hidden="true">{CHECK_ICON[c.state]}</i>
            <span>{c.label}</span>
            <b>{c.text}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function RunnerRow({ row, rank, nowMs }: { row: ScannerRow; rank: number | null; nowMs: number }) {
  const cat = usePhoneCatalyst(row.symbol, 'gainers', { verdict: row.catalyst, halted: row.halted === true, nowMs });
  return (
    <div className="ph-home__runner" data-testid={`phone-runner-${row.symbol}`}>
      <span className="ph-home__runner-rank" aria-label={rank == null ? undefined : `Number ${rank} on Gainers`}>{rank ?? ''}</span>
      <TickerChip symbol={row.symbol} />
      <span className="ph-home__runner-cat" data-tone={cat.tone}>{catalystLine(cat)}</span>
      <span className="ph-home__runner-px">{px(row.price)}</span>
      <span className={`ph-home__runner-chg ${toneClass(row.change_pct == null ? null : row.change_pct * 100, 1)}`}>{pct1(row.change_pct)}</span>
      <RowLink symbol={row.symbol} />
    </div>
  );
}

function orderWords(o: IbkrOrder): string {
  const side = o.side === 'BUY' ? 'Buy' : 'Sell';
  const price = o.limit_price ?? o.stop_price ?? null;
  const at = price != null ? `at ${px(price)}` : formatOrderType(o.order_type).toLowerCase();
  return `${side} ${shares(o.remaining_qty ?? o.qty)} ${at}`;
}

type HoldItem =
  | { kind: 'position'; key: string; position: AccountPosition }
  | { kind: 'order'; key: string; order: IbkrOrder };

function Holdings() {
  const account = usePhoneAccount();
  const { send } = usePhoneSession();
  const boxRef = useRef<HTMLDivElement>(null);
  const fit = useRowsThatFit(boxRef, HOLD_ROW_PX);
  const items: HoldItem[] = [
    ...account.positions.map((position): HoldItem => ({
      kind: 'position', key: `p-${position.symbol}-${position.owner ?? ''}-${position.bot ?? ''}`, position,
    })),
    ...account.working.map((order): HoldItem => ({ kind: 'order', key: `o-${order.order_id}`, order })),
  ];
  const over = items.length > fit;
  const shown = over ? items.slice(0, Math.max(0, fit - 1)) : items;
  return (
    <div className="ph-home__block ph-home__holdings">
      <div className="ph-home__blockhead ph-label">
        <span>Your positions · {account.positions.length}</span>
        <span>Orders · {account.working.length}</span>
      </div>
      <div className="ph-card ph-home__hold" ref={boxRef} data-testid="phone-holdings">
        {!items.length ? (
          <div className="ph-home__holdrow is-note">{account.error ?? 'No positions and no working orders.'}</div>
        ) : null}
        {shown.map((item) => item.kind === 'position' ? (
          <button
            key={item.key}
            type="button"
            className="ph-home__holdrow is-position"
            onClick={() => go({ screen: 'trade', symbol: item.position.symbol })}
          >
            <b>{item.position.symbol}</b>
            <span className="ph-who" data-owner={item.position.owner ?? 'you'}>
              {item.position.owner === 'bots' ? 'Bot' : whoName('you', null)}
            </span>
            <span className="ph-muted">{shares(item.position.qty)} at {px(item.position.avgCost)} · now {px(item.position.mark)}</span>
            <b className={toneClass(item.position.unrealized)}>{signedMoney(item.position.unrealized)}</b>
          </button>
        ) : (
          <div key={item.key} className="ph-home__holdrow is-order">
            <span><span className="ph-muted">Working</span> · <b>{item.order.symbol}</b> · {orderWords(item.order)}</span>
            <button
              type="button"
              className="ph-pill-btn is-danger"
              onClick={() => send(`Cancel ${item.order.symbol} ${orderWords(item.order)}`,
                (door) => door.cancelOrder(item.order.order_id, `${item.order.symbol} ${orderWords(item.order)}`))}
            >
              Cancel
            </button>
          </div>
        ))}
        {over ? (
          <button type="button" className="ph-home__holdrow is-more" onClick={() => go({ screen: 'account' })}>
            {items.length - shown.length} more in Account ›
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function HomeScreen() {
  const feed = useLiveScannerFeed();
  const { exchangeFilter } = useSettings();
  const account = usePhoneAccount();
  const limit = usePhoneLossLimit(account.venue);
  const board = useMarketBoard(DEFAULT_PERIODS);
  const now = useMinuteClock();

  // Home's rows are the top of Gainers: that is the list whose prices must keep moving here.
  const { setL1ActiveTab } = feed;
  useEffect(() => {
    setL1ActiveTab('gainers');
  }, [setL1ActiveTab]);

  const runners = exchangeFilter.filterRows(feed.gainers).slice(0, RUNNERS);
  // Each row's number is its place on Gainers as the scanner serves it.
  const gainerRank = new Map(feed.gainers.map((r, i) => [r.symbol, i + 1]));
  return (
    <PhoneScreen
      name="home"
      tab="home"
      header={(
        <div className="ph-head ph-home__head">
          <VenuePill />
          <div className="ph-head__title">Nova</div>
          <div className="ph-head__sub">{sessionLine(now, board.data?.session ?? null)}</div>
          <div className="ph-grow" />
          <LinkPill />
          <PadlockButton />
          <button type="button" className="ph-icon-btn" aria-label="Settings" onClick={() => go({ screen: 'settings' })}>
            <Settings size={18} aria-hidden="true" />
          </button>
        </div>
      )}
    >
      <div className="ph-home">
        <button type="button" className="ph-card ph-home__money" onClick={() => go({ screen: 'account' })} data-testid="phone-home-money">
          <span>
            <i>Today</i>
            <b className={`is-big ${toneClass(account.dayPnl)}`}>{signedMoney(account.dayPnl)}</b>
          </span>
          <span>
            <i>Open</i>
            <b className={toneClass(account.openPnl)}>{signedMoney(account.openPnl)}</b>
          </span>
          <span>
            <i>Loss limit ›</i>
            <b className={limit.stopped ? 'ph-bad' : limit.warned ? 'ph-warn' : ''}>
              {limit.used == null ? '—' : formatMoney(limit.used, 0)}
              <em> / {limit.limit == null ? '—' : formatMoney(limit.limit, 0)}</em>
            </b>
          </span>
        </button>

        <DayReadCard />

        <div className="ph-home__block">
          <div className="ph-home__blockhead ph-label">
            <span>Top small-cap runners</span>
            <button type="button" className="ph-home__all" onClick={() => go({ screen: 'scan' })}>All ›</button>
          </div>
          <div className="ph-card ph-home__runners">
            {runners.length ? runners.map((row) => (
              <RunnerRow key={row.symbol} row={row} rank={gainerRank.get(row.symbol) ?? null} nowMs={feed.now * 1000} />
            )) : (
              <div className="ph-home__holdrow is-note">{feed.restError ?? 'No rows on Gainers right now.'}</div>
            )}
          </div>
        </div>

        <Holdings />
      </div>
    </PhoneScreen>
  );
}
