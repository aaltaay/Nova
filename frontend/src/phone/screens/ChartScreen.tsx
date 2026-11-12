/**
 * The big chart (frozen mockup R2-Charts): the desk's chart on its side, with the timeframe switch,
 * what moves the stock, and the layers the chart draws.
 *
 * Drawn for a phone held sideways. Entering it asks the phone to turn the screen; where the browser
 * will not, and the phone is still upright, the screen says to turn it rather than squeeze a wide
 * chart into a tall one.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { Crosshair, Layers, Minus, MoveUpRight, RotateCw, Slash, SeparatorVertical, Trash2, Zap } from 'lucide-react';
import { CHART_INDICATORS, type ChartIndicatorId } from '../../constants';
import { useTickerStream } from '../../hooks/useTickerStream';
import { computeQuoteMetrics } from '../../modules';
import { fmtRvol } from '../../utils/quoteFormat';
import { useWorkspace } from '../../workspace';
import { BackButton, LinkPill, PhoneBannerView, TickerChip, VenuePill } from '../PhoneChrome';
import { FrameSwitch, PhoneChart, usePhoneChartPrefs } from '../PhoneChart';
import { catalystLine } from '../phoneCatalyst';
import { useViewport } from '../phoneFit';
import { pct1, px, toneOf } from '../phoneFormat';
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

/** Ask the phone to turn the screen while this screen is up. Browsers allow it only for an installed page. */
function useSideways(): void {
  useEffect(() => {
    const orientation = window.screen?.orientation as (ScreenOrientation & OrientationLock) | undefined;
    orientation?.lock?.('landscape').catch((err: unknown) => console.debug('[Nova phone] the screen was not turned', err));
    return () => {
      try {
        orientation?.unlock?.();
      } catch (err) {
        console.debug('[Nova phone] the screen lock was not released', err);
      }
    };
  }, []);
}

export function ChartScreen({ symbol }: { symbol: string }) {
  useSideways();
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
  if (!sideways) {
    return (
      <div className="ph-screen" data-testid="phone-screen-chart">
        <div className="ph-head has-back">{back}<TickerChip symbol={symbol} /></div>
        <div className="ph-bigchart__turn" role="status">
          <RotateCw size={28} aria-hidden="true" />
          <b>Turn your phone sideways</b>
          <span>The big chart is drawn wide. If the screen does not turn, switch auto-rotate on.</span>
        </div>
      </div>
    );
  }

  const m = detail ? computeQuoteMetrics(detail, discoveryProvider) : null;
  const tone = toneOf(m?.mainChangePct == null ? null : m.mainChangePct * 100, 1) || 'flat';
  const rvol = fmtRvol(detail?.rel_volume);

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
      </div>
      <a className="ph-stock__cat ph-bigchart__cat" data-tone={cat.tone} href={cat.url ?? undefined} target="_blank" rel="noreferrer noopener">
        <Zap size={12} aria-hidden="true" />
        <b>{catalystLine(cat)}</b>
        <span>{cat.headline ?? ''}</span>
        {cat.url ? <i aria-hidden="true">›</i> : null}
      </a>
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
          {layers ? (
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
          ) : null}
        </div>
      </div>
      <PhoneBannerView />
    </div>
  );
}
