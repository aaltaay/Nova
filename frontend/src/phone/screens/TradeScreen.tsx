/**
 * Trade (frozen mockup R2-Trade): one stock's chart, Level 2, tape and the order ticket on one screen that
 * never scrolls. The book and the tape are the desk's own sockets; every order is the desk's own ticket
 * code, sent through the phone's door after the operator's PIN. Paper only (ADR 070).
 *
 * The grab handle under the chart trades chart height for book rows. Every tap is answered by the banner:
 * Sending, Sent once the desk has it, Filled when the position changes, or NOT SENT in the desk's words.
 */
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { ArrowLeftRight, TriangleAlert } from 'lucide-react';
import { CHART_EMA_COLORS, CHART_EMA_LENGTHS, CHART_VWAP_COLOR } from '../../constants';
import { useTickerStream } from '../../hooks/useTickerStream';
import { computeQuoteMetrics } from '../../modules';
import { fmtVolume, sessionPriceOrNull } from '../../utils/quoteFormat';
import { plainPrice } from '../../utils/priceTick';
import { readPref, writePref } from '../../utils/prefStore';
import { useWorkspace } from '../../workspace';
import { LinkPill, PadlockButton, PhoneScreen, VenuePill } from '../PhoneChrome';
import { PHONE_FRAMES, PhoneChart, usePhoneChartPrefs } from '../PhoneChart';
import { linkTone } from '../phoneLink';
import { compact, pct1, px, rvolShort, toneOf } from '../phoneFormat';
import { cleanSymbol, go } from '../phoneRoute';
import { usePhoneSession } from '../PhoneSession';
import { usePhoneAccount } from '../usePhoneAccount';
import { TradeBook, TradeTape } from '../trade/TradeBook';
import { TradeAsk, TradeDots, type Ask } from '../trade/TradeDots';
import { TradeTicket } from '../trade/TradeTicket';
import { cancelAll, flatten } from '../trade/tradeActions';
import { useLevel2Age, usePhoneTrade } from '../trade/usePhoneTrade';
import './trade.css';

const SYMBOL_KEY = 'nova.phone.trade.symbol';
const FRAME_KEY = 'nova.phone.trade.frame';
const CHART_KEY = 'nova.phone.trade.chart';
/** The chart's height: the mockup's small and big, and anything between them by the handle. */
const CHART_MIN = 92;
const CHART_MAX = 172;

function ms(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '…';
  return value < 1_000 ? `${Math.round(value)} ms` : `${(value / 1_000).toFixed(1)} s`;
}

/** How fresh the screen is: the book's age on arrival, and how long the PC takes to answer a tap. */
function DataTapPill({ symbol, behind }: { symbol: string; behind: boolean }) {
  const { link } = usePhoneSession();
  const data = useLevel2Age(symbol);
  const tone = behind || linkTone(link) === 'down' ? 'down' : linkTone(link) === 'slow' ? 'slow' : linkTone(link);
  return (
    <div className="ph-trade__fresh" data-tone={tone} role="status" data-testid="phone-fresh" aria-label={`Level 2 is ${ms(data)} old. The PC answers a tap in ${ms(link.roundTrip?.p50)}`}>
      <span>Data</span><b>{ms(data)}</b>
      <span>Tap</span><b>{ms(link.roundTrip?.p50)}</b>
    </div>
  );
}

/**
 * Says a fill when your position in the stock changes while the screen is up. The first position read, and the
 * first after the account stopped being current, is where you stand, not a fill.
 */
function useFillBanner(symbol: string, heldQty: number, avgCost: number | null, current: boolean): void {
  const { notify } = usePhoneSession();
  const seen = useRef<{ qty: number } | null>(null);
  useEffect(() => {
    const before = seen.current;
    if (!before || !current) {
      seen.current = current ? { qty: heldQty } : null;
      return;
    }
    if (before.qty === heldQty) return;
    seen.current = { qty: heldQty };
    const delta = heldQty - before.qty;
    const did = `${delta > 0 ? 'Bought' : 'Sold'} ${Math.abs(delta).toLocaleString('en-US')} ${symbol}`;
    // From flat, the average is the fill. An add or a sell does not say its own price here.
    const at = before.qty === 0 && avgCost != null ? ` at ${plainPrice(avgCost)}` : '';
    const nowHolds = heldQty === 0
      ? 'Now flat'
      : `Now ${heldQty > 0 ? 'long' : 'short'} ${Math.abs(heldQty).toLocaleString('en-US')}${avgCost != null ? ` · Avg ${plainPrice(avgCost)}` : ''}`;
    notify({ tone: 'filled', title: `Filled · ${did}${at}`, note: nowHolds });
  }, [symbol, heldQty, avgCost, current, notify]);
}

function TradeFor({ symbol }: { symbol: string }) {
  const session = usePhoneSession();
  const { detail } = useTickerStream(symbol);
  const { discoveryProvider } = useWorkspace();
  const trade = usePhoneTrade(symbol);
  const account = usePhoneAccount();
  const prefs = usePhoneChartPrefs();
  const [frame, setFrameState] = useState<string>(() => readPref<string>(FRAME_KEY, '1Min', (raw) => (PHONE_FRAMES.some((f) => f.id === raw) ? (raw as string) : null)));
  const [chartH, setChartH] = useState<number>(() => readPref<number>(CHART_KEY, CHART_MIN, (raw) => (typeof raw === 'number' && raw >= CHART_MIN && raw <= CHART_MAX ? raw : null)));
  const [ask, setAsk] = useState<Ask | null>(null);
  const drag = useRef<{ y: number; h: number; scale: number; moved: boolean } | null>(null);

  const m = detail ? computeQuoteMetrics(detail, discoveryProvider) : null;
  const tone = toneOf(m?.mainChangePct == null ? null : m.mainChangePct * 100, 1) || 'flat';
  const daily = detail?.snapshot?.daily_bar ?? null;
  const avg = trade.position?.avg_cost ?? null;
  useFillBanner(symbol, trade.heldQty, avg, trade.accountCurrent);

  const setFrame = (id: string): void => {
    writePref(FRAME_KEY, id);
    setFrameState(id);
  };
  // The small chart has room for candles and the lines over them, not for a second pane under them.
  const lines = prefs.indicators.filter((id) => id === 'emas' || id === 'vwap');

  const onHandleDown = (ev: ReactPointerEvent<HTMLButtonElement>): void => {
    ev.currentTarget.setPointerCapture(ev.pointerId);
    const screen = ev.currentTarget.closest<HTMLElement>('.ph-screen');
    const scale = screen && screen.offsetHeight ? screen.getBoundingClientRect().height / screen.offsetHeight : 1;
    drag.current = { y: ev.clientY, h: chartH, scale: scale || 1, moved: false };
  };
  const onHandleMove = (ev: ReactPointerEvent<HTMLButtonElement>): void => {
    const d = drag.current;
    if (!d) return;
    const dy = (ev.clientY - d.y) / d.scale;
    if (!d.moved && Math.abs(dy) < 5) return;
    d.moved = true;
    setChartH(Math.round(Math.min(CHART_MAX, Math.max(CHART_MIN, d.h + dy))));
  };
  const onHandleUp = (): void => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    // A tap flips between the two sizes; a drag keeps where it was let go.
    const next = d.moved ? chartH : chartH > (CHART_MIN + CHART_MAX) / 2 ? CHART_MIN : CHART_MAX;
    setChartH(next);
    writePref(CHART_KEY, next);
  };

  const confirm = (): void => {
    const what = ask;
    setAsk(null);
    if (what === 'flatten') trade.act(`Flatten ${symbol}`, flatten());
    else if (what === 'cancel') trade.act('Cancel all orders', cancelAll(), 'done');
  };

  return (
    <PhoneScreen
      name="trade"
      tab="trade"
      header={(
        <div className="ph-head ph-trade__head">
          <VenuePill />
          <button type="button" className="ph-head__title ph-tickerword" aria-label={`Open ${symbol}'s stock page`} onClick={() => go({ screen: 'stock', symbol })}>{symbol}</button>
          <b className="ph-trade__px" data-tone={tone}>{px(m?.mainPrice)}</b>
          <i className="ph-trade__pct" data-tone={tone}>{pct1(m?.mainChangePct)}</i>
          <span className="ph-grow" />
          <DataTapPill symbol={symbol} behind={Boolean(trade.lag)} />
          <PadlockButton />
        </div>
      )}
    >
      <div className="ph-trade__stats">
        <span>Float <b>{fmtVolume(detail?.fundamentals?.float_shares)}</b></span>
        <span>Vol <b>{compact(daily?.volume)}</b></span>
        <span>RVOL <b>{rvolShort(detail?.rel_volume) || '—'}</b></span>
        <span>High <b>{px(sessionPriceOrNull(daily?.high))}</b></span>
        <span>Low <b>{px(sessionPriceOrNull(daily?.low))}</b></span>
      </div>

      {trade.lag ? (
        <div className="ph-trade__lag" role="alert" data-testid="phone-lag">
          <TriangleAlert size={20} aria-hidden="true" />
          <div>
            {/* The desk's first sentence says what is behind; the rest of it is what the buttons below already say. */}
            <b>{trade.lag.split(/(?<=\.)\s/)[0]}</b>
            <span>{trade.heldQty < 0 ? 'A buy that covers, Flatten and Cancel still work.' : 'Buys are held. Sell, Flatten and Cancel still work.'}</span>
          </div>
        </div>
      ) : null}

      <div className="ph-trade__chart" style={{ height: chartH }} data-dim={trade.lag ? 'true' : 'false'}>
        <div className="ph-trade__charthead">
          <div role="group" aria-label="Timeframe">
            {PHONE_FRAMES.map((f) => (
              <button key={f.id} type="button" aria-pressed={f.id === frame} onClick={() => setFrame(f.id)}>{f.name}</button>
            ))}
          </div>
          <div className="ph-trade__legend">
            {lines.includes('emas') ? CHART_EMA_LENGTHS.slice(0, 2).map((n, i) => (
              <span key={n}><i style={{ background: CHART_EMA_COLORS[n] }} />{i === 0 ? `EMA ${n}` : n}</span>
            )) : null}
            {lines.includes('vwap') ? <span><i style={{ background: CHART_VWAP_COLOR }} />VWAP</span> : null}
            {avg != null && trade.heldQty ? <span className="is-avg"><i />Avg {plainPrice(avg)}</span> : null}
          </div>
        </div>
        <div className="ph-trade__chartbody">
          <PhoneChart symbol={symbol} frame={frame} indicators={lines} onIndicatorToggle={prefs.toggleIndicator} mini />
          <button type="button" className="ph-trade__open" aria-label="Open the full chart" onClick={() => go({ screen: 'chart', symbol })} />
        </div>
      </div>
      <button
        type="button"
        className="ph-trade__handle"
        aria-label="Resize the chart: drag up or down"
        data-testid="phone-chart-handle"
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        onPointerCancel={() => { drag.current = null; }}
      >
        <span />
      </button>

      <div className="ph-trade__market">
        <TradeBook symbol={symbol} book={trade.book} why={trade.bookWhy} dim={Boolean(trade.lag)} />
        <TradeTape prints={trade.tape.prints} why={trade.tape.error} />
      </div>

      <TradeTicket
        trade={trade}
        buyingPower={account.figures.buyingPower}
        onFlatten={() => setAsk('flatten')}
        onCancelAll={() => setAsk('cancel')}
      />

      <TradeDots trade={trade} onAsk={setAsk} />
      {ask && session.venue === 'paper' ? <TradeAsk ask={ask} trade={trade} onNo={() => setAsk(null)} onYes={confirm} /> : null}
    </PhoneScreen>
  );
}

export function TradeScreen({ symbol }: { symbol: string | null }) {
  // The Trade tab opens the stock traded last; a ticker chip or a row's Trade button names its own.
  const [last] = useState<string | null>(() => readPref<string | null>(SYMBOL_KEY, null, (raw) => cleanSymbol(typeof raw === 'string' ? raw : null)));
  const sym = symbol ?? last;
  useEffect(() => {
    if (symbol) writePref(SYMBOL_KEY, symbol);
  }, [symbol]);

  if (!sym) {
    return (
      <PhoneScreen
        name="trade"
        tab="trade"
        header={(
          <div className="ph-head">
            <VenuePill />
            <div className="ph-head__title">Trade</div>
            <div className="ph-grow" />
            <LinkPill live />
            <PadlockButton />
          </div>
        )}
      >
        <div className="ph-trade-pick" data-testid="phone-trade-pick">
          <span className="ph-trade-pick__icon" aria-hidden="true"><ArrowLeftRight size={22} /></span>
          <b>Pick a stock to trade</b>
          <p>Tap a blue ticker chip on any list.</p>
          <button type="button" onClick={() => go({ screen: 'scan' })}>Open Scan</button>
        </div>
      </PhoneScreen>
    );
  }
  return <TradeFor key={sym} symbol={sym} />;
}
