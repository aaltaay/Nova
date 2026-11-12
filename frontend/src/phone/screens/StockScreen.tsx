/**
 * The stock page (frozen mockup R2-Stock): one stock before you trade it. The quote, the day's
 * numbers, what is moving it, the desk's own chart, and the way into the Trader.
 *
 * The bid and ask here are the quote Nova read when the page opened: Level 1 sends no fresh bid or
 * ask after that, and Level 2 is opened only on the Trade screen (it holds one of the desk's three
 * books). So once they are more than a moment old the strip turns grey and says how old they are.
 */
import { useEffect, useRef, useState } from 'react';
import { ArrowLeftRight, Layers, Maximize2, Newspaper, Star, X, Zap } from 'lucide-react';
import { CHART_EMA_COLORS, CHART_EMA_LENGTHS, CHART_INDICATORS, CHART_VWAP_COLOR } from '../../constants';
import { useCatalystRead } from '../../hooks/useCatalystRead';
import { useTickerStream } from '../../hooks/useTickerStream';
import { howListed, useHotList } from '../../hot_list';
import { computeQuoteMetrics } from '../../modules';
import type { NewsArticle, TickerDetail } from '../../types/ticker';
import { catalystFace } from '../../utils/catalystCause';
import { fmtMarketCap, fmtRvol, fmtVolume, sessionPriceOrNull } from '../../utils/quoteFormat';
import { useWorkspace } from '../../workspace';
import { BackButton, LinkPill, PhoneScreen, VenuePill } from '../PhoneChrome';
import { FrameSwitch, PhoneChart, usePhoneChartPrefs } from '../PhoneChart';
import { catalystLine, phoneCatalyst } from '../phoneCatalyst';
import { agoShort, pct1, px, toneOf } from '../phoneFormat';
import { go } from '../phoneRoute';
import { useRowsThatFit } from '../useRowsThatFit';
import './stock.css';

/** A bid or ask older than this is no longer "the" bid or ask. */
const QUOTE_FRESH_MS = 3_000;
const STAR_FROM_PC = 'Starring from the phone comes with the Trade build. Star it on the PC; it shows here.';
const NEWS_ROW_PX = 52;

function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(timer);
  }, [ms]);
  return now;
}

function ageWord(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  return sec < 60 ? `${sec}s old` : `${Math.floor(sec / 60)}m old`;
}

function BidAsk({ detail, nowMs }: { detail: TickerDetail | null; nowMs: number }) {
  const quote = detail?.snapshot?.latest_quote ?? null;
  const at = quote?.timestamp ? Date.parse(quote.timestamp) : Number.NaN;
  const age = Number.isFinite(at) ? nowMs - at : null;
  const fresh = age != null && age <= QUOTE_FRESH_MS;
  const old = age == null ? '' : fresh ? '' : ` · ${ageWord(age)}`;
  return (
    <div className="ph-stock__bidask" data-fresh={fresh ? 'true' : 'false'} data-testid="phone-bidask">
      <div className="is-bid">
        <i>BID{old}</i>
        <span>{quote?.bid_size ?? ''}</span>
        <b>{px(quote?.bid_price)}</b>
      </div>
      <div className="is-ask">
        <b>{px(quote?.ask_price)}</b>
        <span>{quote?.ask_size ?? ''}</span>
        <i>ASK</i>
      </div>
    </div>
  );
}

function NewsSheet({ symbol, news, nowMs, onClose }: { symbol: string; news: NewsArticle[]; nowMs: number; onClose: () => void }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const fit = useRowsThatFit(boxRef, NEWS_ROW_PX);
  return (
    <div className="ph-sheet ph-stock__sheet" role="dialog" aria-modal="true" aria-label={`News for ${symbol}`}>
      <div className="ph-stock__news">
        <div className="ph-stock__news-head">
          <b>News · {symbol}</b>
          <button type="button" className="ph-icon-btn" aria-label="Close" onClick={onClose}><X size={18} aria-hidden="true" /></button>
        </div>
        <div className="ph-stock__news-list" ref={boxRef}>
          {!news.length ? <div className="ph-empty">No news on file for {symbol}.</div> : news.slice(0, fit).map((n) => (
            <a key={`${n.url}-${n.created_at}`} href={n.url} target="_blank" rel="noreferrer noopener">
              <span>{n.headline}</span>
              <i>{n.source} · {agoShort(nowMs - Date.parse(n.created_at))}</i>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}

export function StockScreen({ symbol }: { symbol: string }) {
  const { detail, loading, fetchFailed } = useTickerStream(symbol);
  const { discoveryProvider } = useWorkspace();
  const hot = useHotList();
  const chart = usePhoneChartPrefs();
  const read = useCatalystRead(symbol, null);
  const nowMs = useNow(1_000);
  const [menu, setMenu] = useState(false);
  const [news, setNews] = useState(false);

  const m = detail ? computeQuoteMetrics(detail, discoveryProvider) : null;
  const daily = detail?.snapshot?.daily_bar ?? null;
  const f = detail?.fundamentals ?? null;
  const tone = toneOf(m?.mainChangePct == null ? null : m.mainChangePct * 100, 1);
  const halt = detail?.halt?.halted ? detail.halt : null;
  const verdict = read.read?.facts?.catalyst ?? null;
  const cat = phoneCatalyst({
    face: catalystFace(read.read, verdict, nowMs, read.loading),
    verdict,
    halted: Boolean(halt),
    resumeTs: halt?.exchange?.trade_resume ?? halt?.exchange?.quote_resume ?? null,
    nowMs,
  });
  const starred = howListed(hot.view, symbol) === 'star';
  const stats = [
    { name: 'Prev close', value: px(m?.prevClose) },
    { name: 'Gap', value: pct1(m?.gapPct) },
    { name: 'Short', value: f?.short_percent_of_float != null ? `${(f.short_percent_of_float * 100).toFixed(1)}%` : '—' },
    { name: 'Mkt cap', value: fmtMarketCap(f?.market_cap).replace('$', '') },
  ];

  return (
    <PhoneScreen
      name="stock"
      tab={null}
      header={(
        <div className="ph-head has-back">
          <BackButton to={{ screen: 'scan' }} label="Back" />
          <VenuePill />
          <div className="ph-head__title">{symbol}</div>
          <div className="ph-head__sub">{detail?.asset?.exchange ?? ''}</div>
          <div className="ph-grow" />
          <LinkPill />
          <button
            type="button"
            className="ph-icon-btn ph-stock__star"
            data-on={starred ? 'true' : 'false'}
            aria-label={starred ? `${symbol} is on your hot list` : `${symbol} is not on your hot list`}
            aria-disabled="true"
            data-why={STAR_FROM_PC}
          >
            <Star size={18} fill={starred ? 'currentColor' : 'none'} aria-hidden="true" />
          </button>
        </div>
      )}
    >
      <div className="ph-stock__quote" data-testid="phone-stock-quote">
        <div className="ph-stock__price">
          <b data-tone={tone || 'flat'}>{m ? px(m.mainPrice) : loading ? '…' : '—'}</b>
          <span>
            <i data-tone={tone || 'flat'}>{pct1(m?.mainChangePct)}</i>
            <em data-tone={tone || 'flat'}>{m?.mainChangeAbs != null ? `${m.mainChangeAbs > 0 ? '+' : ''}${m.mainChangeAbs.toFixed(2)}` : ''}</em>
          </span>
        </div>
        <div className="ph-stock__day">
          <span>High / Low</span><b>{px(sessionPriceOrNull(daily?.high))} / {px(sessionPriceOrNull(daily?.low))}</b>
          <span>Volume</span><b>{fmtVolume(daily?.volume)}{fmtRvol(detail?.rel_volume) ? ` · ${fmtRvol(detail?.rel_volume)}` : ''}</b>
          <span>Float</span><b>{fmtVolume(f?.float_shares)}</b>
        </div>
      </div>

      {fetchFailed && !detail ? (
        <div className="ph-stock__cat is-bad" role="alert">Nova could not read {symbol}. Check the link, then go back and open it again.</div>
      ) : (
        <a
          className="ph-stock__cat"
          data-tone={cat.tone}
          href={cat.url ?? undefined}
          target="_blank"
          rel="noreferrer noopener"
          data-testid="phone-stock-catalyst"
        >
          <Zap size={13} aria-hidden="true" />
          <b>{catalystLine(cat)}</b>
          <span>{cat.headline ?? ''}</span>
          {cat.url ? <i aria-hidden="true">›</i> : null}
        </a>
      )}

      <div className="ph-stock__chartcard">
        <div className="ph-stock__legend">
          {chart.indicators.includes('emas') ? (
            <>
              <span className="ph-faint">EMA</span>
              {CHART_EMA_LENGTHS.map((n) => <span key={n}><i style={{ background: CHART_EMA_COLORS[n] }} />{n}</span>)}
            </>
          ) : null}
          {chart.indicators.includes('vwap') ? <span><i style={{ background: CHART_VWAP_COLOR }} />VWAP</span> : null}
          <span className="ph-grow" />
          <button type="button" onClick={() => go({ screen: 'chart', symbol })} aria-label="Open the big chart">
            <Maximize2 size={12} aria-hidden="true" />Big chart
          </button>
        </div>
        <PhoneChart symbol={symbol} frame={chart.frame} indicators={chart.indicators} onIndicatorToggle={chart.toggleIndicator} />
      </div>

      <div className="ph-stock__controls">
        <FrameSwitch frame={chart.frame} onFrame={chart.setFrame} />
        <span className="ph-grow" />
        <button type="button" className="ph-stock__ind" aria-expanded={menu} aria-label="Indicators: choose what the chart shows" onClick={() => setMenu(!menu)}>
          <Layers size={14} aria-hidden="true" />Indicators
        </button>
        {menu ? (
          <div className="ph-menu ph-stock__indmenu" role="menu">
            {CHART_INDICATORS.map((o) => (
              <button key={o.id} type="button" role="menuitemcheckbox" aria-checked={chart.indicators.includes(o.id)} onClick={() => chart.toggleIndicator(o.id)}>
                {o.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <BidAsk detail={detail} nowMs={nowMs} />

      <div className="ph-card ph-stock__stats">
        {stats.map((s) => <div key={s.name}><i>{s.name}</i><b>{s.value}</b></div>)}
      </div>

      <div className="ph-stock__actions">
        <button type="button" className="ph-stock__trade" onClick={() => go({ screen: 'trade', symbol })} data-testid="phone-stock-trade">
          <ArrowLeftRight size={18} strokeWidth={2.2} aria-hidden="true" />Trade {symbol}
        </button>
        <button type="button" className="ph-card ph-stock__newsbtn" aria-label={`News for ${symbol}`} onClick={() => setNews(true)}>
          <Newspaper size={20} aria-hidden="true" />
        </button>
      </div>

      {news ? <NewsSheet symbol={symbol} news={detail?.news ?? []} nowMs={nowMs} onClose={() => setNews(false)} /> : null}
    </PhoneScreen>
  );
}
