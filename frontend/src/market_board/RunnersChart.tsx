/**
 * Runners per session, by theme (ADR 053; amendment 2026-10-13 evening, operator: "the runners per session is so
 * tiny no hover, no maximizing"): the small-cap climate card's full width, each session's runners by theme in a
 * hover card, and -- on a click or the corner button -- a large view with an axis, every date, every bar's count and
 * the themes' legend. A session Nova holds no Gainers board for is filled from the Massive day movers index, drawn
 * lighter and outlined and labelled so (amendment 2026-10-14); one Massive has not built either is hatched and says
 * so: never drawn as a zero.
 */
import { useCallback, useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { Maximize2, X } from 'lucide-react';
import {
  RUNNERS_FROM_MASSIVE,
  RUNNERS_NOT_RECORDED,
  RUNNERS_SOURCE_MASSIVE,
  RUNNERS_TIP_THEMES,
  THEME_OTHER_COLOR,
} from './constants';
import { shortDate } from './format';
import type { Climate } from './types';

type Day = Climate['days'][number];
export type ThemeColor = (theme: string) => string;

interface Frame {
  W: number;
  H: number;
  /** Room for the axis labels on the left. */
  left: number;
  /** Room above the tallest bar (its count). */
  head: number;
  big: boolean;
}

const SMALL: Frame = { W: 560, H: 74, left: 0, head: 2, big: false };
const LARGE: Frame = { W: 1040, H: 320, left: 34, head: 16, big: true };
const TICKS_H = 15;

export function dayWords(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC',
  });
}

/** A round top for the large view's axis: 1, 2, 2.5, 4, 5 or 10 times a power of ten, at or above `max`. */
export function axisTop(max: number): number {
  const mag = 10 ** Math.floor(Math.log10(Math.max(1, max)));
  for (const step of [1, 2, 2.5, 4, 5, 10]) {
    if (step * mag >= max) return step * mag;
  }
  return 10 * mag;
}

/** A session's themes, most runners first (the bottom of its bar). */
export function themesOf(d: Day): [string, number][] {
  return Object.entries(d.themes).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
}

function layout(f: Frame, n: number) {
  const plotW = f.W - f.left;
  const gap = Math.max(2, (plotW / Math.max(n, 1)) * 0.14);
  const bw = (plotW - gap * (n - 1)) / Math.max(n, 1);
  return { gap, bw, x: (i: number) => f.left + i * (bw + gap) };
}

function Tip({ d, color, xPct }: { d: Day; color: ThemeColor; xPct: number }) {
  const parts = themesOf(d);
  const shown = parts.slice(0, RUNNERS_TIP_THEMES);
  const rest = parts.slice(RUNNERS_TIP_THEMES);
  const restRunners = rest.reduce((a, [, v]) => a + v, 0);
  const edge = xPct < 20 ? 'left' : xPct > 80 ? 'right' : 'mid';
  return (
    <div className={`mk-runners__tip is-${edge}`} role="tooltip" style={{ left: `${xPct}%` }} data-testid="runners-tip">
      <div className="mk-runners__tiphead">
        <b>{dayWords(d.date)}</b>
        {d.source ? <span>{d.total ?? 0} runner{d.total === 1 ? '' : 's'}</span> : null}
      </div>
      {!d.source ? <p className="mk-muted">{RUNNERS_NOT_RECORDED}</p> : null}
      {d.source === RUNNERS_SOURCE_MASSIVE ? <p className="mk-muted" data-testid="runners-tip-massive">{RUNNERS_FROM_MASSIVE}</p> : null}
      {d.source && parts.length === 0 ? <p className="mk-muted">no 20%+ runners</p> : null}
      {shown.length ? (
        <ul>
          {shown.map(([name, v]) => (
            <li key={name}><i style={{ background: color(name) }} /><span>{name}</span><b>{v}</b></li>
          ))}
        </ul>
      ) : null}
      {rest.length ? <p className="mk-muted">+ {restRunners} in {rest.length} more theme{rest.length > 1 ? 's' : ''}</p> : null}
    </div>
  );
}

function Chart({ c, color, f, onOpen }: { c: Climate; color: ThemeColor; f: Frame; onOpen?: () => void }) {
  const [hover, setHover] = useState<number | null>(null);
  const hatch = `mk-hatch-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const n = c.days.length;
  const { gap, bw, x } = layout(f, n);
  const max = Math.max(1, ...c.days.map((d) => d.total ?? 0));
  const top = f.big ? axisTop(max) : max;
  const room = f.H - f.head;
  const y = (v: number) => f.H - (v / top) * room;
  const lit = Math.min(c.sessions, n);
  const recorded = c.days.filter((d) => d.source && d.source !== RUNNERS_SOURCE_MASSIVE).length;
  const hovered = hover != null ? c.days[hover] : null;
  return (
    <div className={`mk-runners__plot${onOpen ? ' is-zoom' : ''}`} onClick={onOpen} onMouseLeave={() => setHover(null)}>
      <svg className="mk-runners__svg" viewBox={`0 0 ${f.W} ${f.H + TICKS_H}`} role="img"
        aria-label={`Runners per session by theme, last ${n} sessions, ${recorded} recorded`}>
        <defs>
          <pattern id={hatch} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="5" className="mk-runners__hatch" />
          </pattern>
        </defs>
        {f.big ? [0, top / 2, top].map((v) => (
          <g key={v}>
            <line x1={f.left} x2={f.W} y1={y(v)} y2={y(v)} className="mk-runners__grid" />
            <text x={f.left - 6} y={y(v) + 3} textAnchor="end" className="mk-runners__axis">{v}</text>
          </g>
        )) : null}
        {c.days.map((d, i) => {
          const bx = x(i);
          const on = i >= n - lit;
          const dim = hover != null && hover !== i;
          let yy = f.H;
          const massive = d.source === RUNNERS_SOURCE_MASSIVE;
          return (
            <g key={d.date} opacity={dim ? 0.35 : on ? 1 : 0.45} data-testid={`runners-day-${d.date}`}
              className={massive ? 'is-massive' : undefined}>
              {d.source ? themesOf(d).map(([name, v]) => {
                const h = (v / top) * room;
                yy -= h;
                return <rect key={name} x={bx} y={yy} width={bw} height={h} fill={color(name)} />;
              }) : (
                <rect x={bx} y={f.head} width={bw} height={room} fill={`url(#${hatch})`} className="mk-runners__none" />
              )}
              {massive && d.total ? (
                <rect x={bx + 0.5} y={yy + 0.5} width={Math.max(0, bw - 1)} height={Math.max(0, f.H - yy - 1)}
                  className="mk-runners__massive" />
              ) : null}
              {f.big && d.source && d.total != null ? (
                <text x={bx + bw / 2} y={yy - 4} textAnchor="middle" className="mk-runners__count">{d.total}</text>
              ) : null}
              {f.big || i % 5 === 0 || i === n - 1 ? (
                <text x={bx + bw / 2} y={f.H + 11} textAnchor="middle" className="mk-climate__tick">
                  {f.big ? shortDate(d.date) : d.date.slice(8)}
                </text>
              ) : null}
              <rect x={bx - gap / 2} y={0} width={bw + gap} height={f.H + TICKS_H} className="mk-runners__hit"
                data-testid={`runners-hit-${d.date}`} onMouseEnter={() => setHover(i)} />
            </g>
          );
        })}
        {lit > 0 && n > 0 ? (
          <rect x={x(n - lit) - 1} y={0.5} width={x(n - 1) + bw - x(n - lit) + 2} height={f.H - 0.5}
            className="mk-climate__lit" />
        ) : null}
      </svg>
      {hovered && hover != null ? <Tip d={hovered} color={color} xPct={((x(hover) + bw / 2) / f.W) * 100} /> : null}
    </div>
  );
}

function LargeView({ c, color, period, onClose }: { c: Climate; color: ThemeColor; period: string; onClose: () => void }) {
  const titleId = useId();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const totals = new Map<string, number>();
  c.days.forEach((d) => themesOf(d).forEach(([k, v]) => totals.set(k, (totals.get(k) ?? 0) + v)));
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]);
  const named = ranked.filter(([k]) => color(k) !== THEME_OTHER_COLOR);
  const other = ranked.filter(([k]) => color(k) === THEME_OTHER_COLOR);
  const otherRunners = other.reduce((a, [, v]) => a + v, 0);
  const runners = ranked.reduce((a, [, v]) => a + v, 0);
  const recorded = c.days.filter((d) => d.source && d.source !== RUNNERS_SOURCE_MASSIVE).length;
  const fromMassive = c.days.filter((d) => d.source === RUNNERS_SOURCE_MASSIVE).length;
  const first = c.days[0]?.date;
  const last = c.days[c.days.length - 1]?.date;
  return createPortal(
    <div className="mk-modal" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="mk-modal__box" role="dialog" aria-modal="true" aria-labelledby={titleId}
        data-testid="market-runners-large">
        <header className="mk-modal__head">
          <h3 id={titleId}>Runners per session, by theme</h3>
          <span className="mk-hint">
            {first && last ? `${shortDate(first)} – ${shortDate(last)} · ` : ''}{c.days.length} sessions, {recorded} recorded
            {fromMassive ? `, ${fromMassive} from Massive` : ''}
            {' · '}{runners} runners of 20%+ on Nova&apos;s Gainers board (top {c.lens.rank_max}, ${c.lens.price_min}+)
            {fromMassive ? " or, on an outlined lighter bar, any listed stock in Massive's minute bars" : ''}
            {' · '}dashed = the {period} on the card · hatched = not recorded
          </span>
          <button type="button" className="mk-icon-btn mk-push" aria-label="Close the large chart" onClick={onClose}
            autoFocus>
            <X size={16} />
          </button>
        </header>
        <Chart c={c} color={color} f={LARGE} />
        <div className="mk-legend mk-modal__legend">
          {named.map(([name, v]) => (
            <span key={name}><b style={{ color: color(name) }}>&#9632;</b> {name} <b>{v}</b></span>
          ))}
          {other.length ? (
            <span><b style={{ color: THEME_OTHER_COLOR }}>&#9632;</b> {other.length} other themes <b>{otherRunners}</b></span>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function RunnersChart({ c, color, period }: { c: Climate; color: ThemeColor; period: string }) {
  const [large, setLarge] = useState(false);
  const close = useCallback(() => setLarge(false), []);
  const open = useCallback(() => setLarge(true), []);
  return (
    <div className="mk-box mk-runners" data-testid="market-runners">
      <div className="mk-runners__head">
        <span className="mk-t">Runners per session, by theme · {c.days.length} sessions</span>
        <span className="mk-s mk-push">hover a bar for its themes · click to enlarge</span>
        <button type="button" className="mk-icon-btn" aria-label="Open the runners chart large" title="Open large"
          onClick={open}>
          <Maximize2 size={13} />
        </button>
      </div>
      <Chart c={c} color={color} f={SMALL} onOpen={open} />
      {large ? <LargeView c={c} color={color} period={period} onClose={close} /> : null}
    </div>
  );
}
