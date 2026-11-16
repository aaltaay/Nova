/**
 * The big chart: the desk's chart filling the phone, with the timeframe switch, what moves the stock,
 * and the layers the chart draws.
 *
 * It opens upright, as the phone is held (operator, 2026-11-12: "instead of asking people to turn the
 * phone around ... it shows the whole thing"). On its side it is the frozen mockup R2-Charts: the phone
 * turned by hand, or the sideways button, which asks the browser for the whole screen and then to turn
 * it. A page may not turn the screen by itself, so the first build's request on entry did nothing.
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowLeftRight, Crosshair, Layers, Minus, MoveUpRight, RectangleHorizontal, RectangleVertical, Slash, SeparatorVertical, Trash2, Zap } from 'lucide-react';
import { CHART_EMA_COLORS, CHART_EMA_LENGTHS, CHART_INDICATORS, CHART_VWAP_COLOR, type ChartIndicatorId } from '../../constants';
import { useTickerStream } from '../../hooks/useTickerStream';
import { computeQuoteMetrics } from '../../modules';
import { fmtRvol } from '../../utils/quoteFormat';
import { useWorkspace } from '../../workspace';
import { BackButton, LinkPill, PhoneBannerView, TickerChip, VenuePill } from '../PhoneChrome';
import { FrameSwitch, PhoneChart, usePhoneChartPrefs } from '../PhoneChart';
import { catalystLine } from '../phoneCatalyst';
import { useViewport } from '../phoneFit';
import { pct1, px, toneOf } from '../phoneFormat';
import { go } from '../phoneRoute';
import { usePhoneCatalyst } from '../usePhoneCatalyst';
import './chart.css';

const DRAW_ON_DESK = 'Drawing from the phone comes in a later build. Lines you draw on the desk show here.';
const ALWAYS_ON = 'Always drawn.';
const NOT_YET = 'Not on the phone yet. The desk has it.';

const TOOLS: readonly { name: string; icon: ReactNode; why?: string }[] = [
  { name: 'Crosshair', icon: <Crosshair size={18} aria-hidden="true" /> },
  { name: 'Trend line', icon: <Slash size={18} aria-hidden="true" />, why: DRAW_ON_DESK },
  { name: 'Horizontal line', icon: <Minus size={18} aria-hidden="true" />, why: DRAW_ON_DESK },
  { name: 'Vertical line', icon: <SeparatorVertical size={18} aria-hidden="true" />, why: DRAW_ON_DESK },
  { name: 'Ray', icon: <MoveUpRight size={18} aria-hidden="true" />, why: DRAW_ON_DESK },
  { name: 'Clear all drawings', icon: <Trash2 size={18} aria-hidden="true" />, why: DRAW_ON_DESK },
];

/** The layers of the frozen mockup. A real switch where the desk chart has one; a reason where it has none. */
const FIXED_LAYERS: readonly { name: string; on: boolean; why: string }[] = [
  { name: 'Position', on: true, why: ALWAYS_ON },
  { name: 'Volume', on: true, why: ALWAYS_ON },
  { name: 'Levels', on: false, why: NOT_YET },
  { name: 'Trends', on: false, why: NOT_YET },
  { name: 'Heat', on: false, why: NOT_YET },
];

interface OrientationLock {
  lock?: (orientation: 'landscape' | 'portrait') => Promise<void>;
  unlock?: () => void;
}

const NOT_TURNED = 'This browser would not turn the screen. Switch auto-rotate on and turn the phone.';

/**
 * Turn the screen on its side for this screen, and back. Browsers turn a page only from a tap and only once it
 * has the whole screen, so `turn` asks for both in that order. `turned` is true while this screen holds the
 * turn; leaving the screen gives it back.
 */
function useSideways(): { turned: boolean; refused: boolean; turn: () => void; upright: () => void } {
  const [turned, setTurned] = useState(false);
  const [refused, setRefused] = useState(false);
  const held = useRef(false);

  const release = useCallback(() => {
    if (!held.current) return;
    held.current = false;
    try {
      (window.screen?.orientation as (ScreenOrientation & OrientationLock) | undefined)?.unlock?.();
    } catch (err) {
      console.debug('[Nova phone] the screen lock was not released', err);
    }
    if (document.fullscreenElement) {
      document.exitFullscreen().catch((err: unknown) => console.debug('[Nova phone] the full screen was not left', err));
    }
  }, []);

  const turn = useCallback(() => {
    const orientation = window.screen?.orientation as (ScreenOrientation & OrientationLock) | undefined;
    const ask = async (): Promise<void> => {
      if (!orientation?.lock) throw new Error('no orientation lock');
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
      held.current = true;
      await orientation.lock('landscape');
    };
    ask().then(() => {
      setRefused(false);
      setTurned(true);
    }).catch((err: unknown) => {
      console.debug('[Nova phone] the screen was not turned', err);
      release();
      setRefused(true);
    });
  }, [release]);

  const upright = useCallback(() => {
    release();
    setTurned(false);
  }, [release]);

  useEffect(() => release, [release]);
  // The Back key leaves the full screen: the turn goes with it.
  useEffect(() => {
    const left = (): void => {
      if (!document.fullscreenElement && held.current) upright();
    };
    document.addEventListener('fullscreenchange', left);
    return () => document.removeEventListener('fullscreenchange', left);
  }, [upright]);

  return { turned, refused, turn, upright };
}

export function ChartScreen({ symbol }: { symbol: string }) {
  const side = useSideways();
  const viewport = useViewport();
  const sideways = viewport.width > viewport.height;
  const { detail } = useTickerStream(symbol);
  const { discoveryProvider } = useWorkspace();
  const chart = usePhoneChartPrefs();
  const [layers, setLayers] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(timer);
  }, []);

  const halt = detail?.halt?.halted ? detail.halt : null;
  const cat = usePhoneCatalyst(symbol, null, {
    halted: Boolean(halt),
    resumeTs: halt?.exchange?.trade_resume ?? halt?.exchange?.quote_resume ?? null,
    nowMs: now,
  });

  const back = <BackButton to={{ screen: 'stock', symbol }} label="Back to the stock page" />;
  const m = detail ? computeQuoteMetrics(detail, discoveryProvider) : null;
  const tone = toneOf(m?.mainChangePct == null ? null : m.mainChangePct * 100, 1) || 'flat';
  const rvol = fmtRvol(detail?.rel_volume);
  const layersMenu = layers ? (
    <div className="ph-bigchart__layers" role="menu" data-testid="phone-chart-layers">
      {CHART_INDICATORS.map((o) => {
        const on = chart.indicators.includes(o.id as ChartIndicatorId);
        return (
          <button key={o.id} type="button" role="menuitemcheckbox" aria-checked={on} onClick={() => chart.toggleIndicator(o.id as ChartIndicatorId)}>
            {o.label}
          </button>
        );
      })}
      {FIXED_LAYERS.map((l) => (
        <button key={l.name} type="button" role="menuitemcheckbox" aria-checked={l.on} disabled data-why={l.why}>{l.name}</button>
      ))}
    </div>
  ) : null;
  const catalyst = (
    <a className="ph-stock__cat ph-bigchart__cat" data-tone={cat.tone} href={cat.url ?? undefined} target="_blank" rel="noreferrer noopener">
      <Zap size={12} aria-hidden="true" />
      <b>{catalystLine(cat)}</b>
      <span>{cat.headline ?? ''}</span>
      {cat.url ? <i aria-hidden="true">›</i> : null}
    </a>
  );

  if (!sideways) {
    return (
      <div className="ph-screen ph-bigchart is-upright" data-testid="phone-screen-chart">
        <div className="ph-head has-back">
          {back}
          <TickerChip symbol={symbol} />
          <b className="ph-bigchart__px" data-tone={tone}>{px(m?.mainPrice)}</b>
          <i className="ph-bigchart__pct" data-tone={tone}>{pct1(m?.mainChangePct)}</i>
          <span className="ph-grow" />
          <LinkPill />
        </div>
        {catalyst}
        <div className="ph-bigchart__box">
          <div className="ph-stock__legend">
            {chart.indicators.includes('emas') ? (
              <>
                <span className="ph-faint">EMA</span>
                {CHART_EMA_LENGTHS.map((n) => <span key={n}><i style={{ background: CHART_EMA_COLORS[n] }} />{n}</span>)}
              </>
            ) : null}
            {chart.indicators.includes('vwap') ? <span><i style={{ background: CHART_VWAP_COLOR }} />VWAP</span> : null}
            {rvol ? <><span className="ph-grow" /><span>RVOL {rvol}</span></> : null}
          </div>
          <PhoneChart symbol={symbol} frame={chart.frame} indicators={chart.indicators} onIndicatorToggle={chart.toggleIndicator} />
          {layersMenu}
          {side.refused ? <div className="ph-bigchart__note" role="status" data-testid="phone-chart-not-turned">{NOT_TURNED}</div> : null}
        </div>
        <div className="ph-bigchart__bar">
          <button type="button" className="ph-bigchart__trade" aria-label={`Trade ${symbol}`} onClick={() => go({ screen: 'trade', symbol })}>
            <ArrowLeftRight size={16} strokeWidth={2.2} aria-hidden="true" />Trade
          </button>
          <FrameSwitch frame={chart.frame} onFrame={chart.setFrame} />
          <span className="ph-grow" />
          <button type="button" className="ph-bigchart__tool" aria-label="Indicators: choose what the chart shows" aria-expanded={layers} aria-pressed={layers} onClick={() => setLayers(!layers)}>
            <Layers size={18} aria-hidden="true" />
          </button>
          <button type="button" className="ph-bigchart__tool" aria-label="Turn the chart sideways" onClick={side.turn}>
            <RectangleHorizontal size={18} aria-hidden="true" />
          </button>
        </div>
        <PhoneBannerView />
      </div>
    );
  }

  return (
    <div className="ph-screen ph-bigchart" data-testid="phone-screen-chart">
      <div className="ph-bigchart__head">
        {back}
        <VenuePill />
        <TickerChip symbol={symbol} />
        <b className="ph-bigchart__px" data-tone={tone}>{px(m?.mainPrice)}</b>
        <i className="ph-bigchart__pct" data-tone={tone}>{pct1(m?.mainChangePct)}</i>
        {rvol ? <span className="ph-bigchart__rvol">RVOL <b>{rvol}</b></span> : null}
        <span className="ph-grow" />
        <FrameSwitch frame={chart.frame} onFrame={chart.setFrame} />
        <LinkPill />
        {side.turned ? (
          <button type="button" className="ph-icon-btn" aria-label="Turn the chart upright" onClick={side.upright}>
            <RectangleVertical size={18} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {catalyst}
      <div className="ph-bigchart__main">
        <div className="ph-bigchart__rail">
          <div className="ph-card">
            {TOOLS.map((t) => (
              <button
                key={t.name}
                type="button"
                aria-label={t.name}
                aria-pressed={!t.why}
                disabled={Boolean(t.why)}
                data-why={t.why}
              >
                {t.icon}
              </button>
            ))}
            <i aria-hidden="true" />
            <button type="button" aria-label="Indicators: choose what the chart shows" aria-expanded={layers} aria-pressed={layers} onClick={() => setLayers(!layers)}>
              <Layers size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
        <div className="ph-bigchart__box">
          <PhoneChart symbol={symbol} frame={chart.frame} indicators={chart.indicators} onIndicatorToggle={chart.toggleIndicator} />
          {layersMenu}
        </div>
      </div>
      <PhoneBannerView />
    </div>
  );
}
