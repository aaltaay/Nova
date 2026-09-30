/**
 * The export dialog's trim timeline (ADR 039, mockup v1 board 4): the
 * moments of the day (the eyes' journal), where the screen recording and the
 * high-quality capture have frames, when the tab showed the symbol and when
 * it showed something else, and a white selection with two handles. The start
 * can move before the clip as far as Nova followed the tab (it keeps 30 min of
 * where each tab was); a stretch it did not follow reads "not followed" and is
 * left out. Clicking a track moves the preview to that moment.
 */
import { useRef, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react';
import { clockLabel, etClock } from './clipModel';
import { CLIP_EXPORT_TRIM, CLIP_EXPORT_TRIM_HINT } from './clipsConstants';
import { clampSelection, timelineScale, timelineTicks } from './clipExportModel';

export type Span = [number, number];
export type TimelineTracks = {
  screen: Span[];
  hq: Span[];
  shown: Span[];
  hidden: { start: number; end: number; showing: string | null; reason: string | null }[];
  /** Where Nova was not following the tab (before the clip's first mark, after its stop); absent from an older main process. */
  unknown?: Span[];
  gaps: Span[];
};
export type Moment = { ts: number; label: string; tone: 'go' | 'target' | 'stop' | 'info' };

/** A hidden stretch's label when the tab showed no other symbol. */
const HIDDEN_WORDS: Record<string, string> = { minimized: 'minimized', page: 'other page', document: 'hidden', closed: 'closed', not_open: 'not shown' };

export function ClipTimeline({ from, to, tracks, moments, symbol, start, end, playhead, onSelect, onPlayhead }: {
  from: number;
  to: number;
  tracks: TimelineTracks;
  moments: Moment[];
  symbol: string;
  start: number;
  end: number;
  playhead: number | null;
  onSelect: (start: number, end: number) => void;
  onPlayhead: (ts: number) => void;
}) {
  const area = useRef<HTMLDivElement>(null);
  const scale = timelineScale(from, to);
  const tsAt = (clientX: number) => {
    const r = area.current?.getBoundingClientRect();
    return r ? scale.ts(((clientX - r.left) / Math.max(1, r.width)) * 100) : from;
  };
  const drag = (which: 'start' | 'end') => (e: ReactPointerEvent<HTMLSpanElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      const t = tsAt(ev.clientX);
      const next = which === 'start' ? clampSelection(t, end, from, to) : clampSelection(start, t, from, to);
      onSelect(Math.round(next.start), Math.round(next.end));
    };
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
  };
  const nudge = (which: 'start' | 'end') => (e: ReactKeyboardEvent<HTMLSpanElement>) => {
    const step = e.shiftKey ? 10 : 1;
    const d = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0;
    if (!d) return;
    e.preventDefault();
    const next = which === 'start' ? clampSelection(start + d, end, from, to) : clampSelection(start, end + d, from, to);
    onSelect(Math.round(next.start), Math.round(next.end));
  };
  const seg = (s: Span, cls: string, key: string, label?: string | null) => (
    <span key={key} className={`clip-tl__seg ${cls}`} style={{ left: `${scale.pct(s[0])}%`, width: `${Math.max(0.2, scale.pct(s[1]) - scale.pct(s[0]))}%` }}>
      {label ? <em>{label}</em> : null}
    </span>
  );
  const click = (e: ReactPointerEvent<HTMLDivElement>) => onPlayhead(Math.round(tsAt(e.clientX)));

  return (
    <div className="clip-tl" data-testid="clip-timeline">
      <div className="clip-tl__head">
        <b>{CLIP_EXPORT_TRIM}</b>
        <span className="clip-tl__muted">{CLIP_EXPORT_TRIM_HINT}</span>
        <span className="clip-tl__span">{etClock(from).slice(0, 5)} – {etClock(to).slice(0, 5)} ET · selected {clockLabel(end - start)}</span>
      </div>
      <div className="clip-tl__grid">
        <div className="clip-tl__names">
          <span />
          <span>Moments <small>eyes&apos; journal</small></span>
          <span>Screen recording <small>15 fps</small></span>
          <span>High quality <small>30 fps</small></span>
          <span>Tab showed {symbol}</span>
        </div>
        <div className="clip-tl__area" ref={area} onPointerDown={click}>
          <div className="clip-tl__ruler">
            {timelineTicks(from, to).map((t) => <span key={t.ts} style={{ left: `${scale.pct(t.ts)}%` }}>{t.label}</span>)}
          </div>
          <div className="clip-tl__track clip-tl__track--moments">
            {moments.map((m, i) => (
              <span key={`${m.ts}-${i}`} className={`clip-tl__moment clip-tl__moment--${m.tone}`} style={{ left: `${scale.pct(m.ts)}%` }} title={`${m.label} · ${etClock(m.ts)}`}>
                {m.label}
              </span>
            ))}
          </div>
          <div className="clip-tl__track">
            {tracks.screen.map((s, i) => seg(s, 'clip-tl__seg--screen', `s${i}`))}
            {tracks.gaps.map((s, i) => seg(s, 'clip-tl__seg--gap', `g${i}`, 'Nova down'))}
          </div>
          <div className="clip-tl__track">{tracks.hq.map((s, i) => seg(s, 'clip-tl__seg--hq', `h${i}`))}</div>
          <div className="clip-tl__track">
            {tracks.shown.map((s, i) => seg(s, 'clip-tl__seg--shown', `v${i}`))}
            {tracks.hidden.map((h, i) => seg([h.start, h.end], 'clip-tl__seg--hidden', `x${i}`, h.showing ?? HIDDEN_WORDS[h.reason ?? ''] ?? 'hidden'))}
            {(tracks.unknown ?? []).map((s, i) => seg(s, 'clip-tl__seg--unknown', `u${i}`, 'not followed'))}
          </div>
          <div className="clip-tl__sel" style={{ left: `${scale.pct(start)}%`, width: `${scale.pct(end) - scale.pct(start)}%` }}>
            <span className="clip-tl__tag clip-tl__tag--l">{etClock(start)}</span>
            <span className="clip-tl__tag clip-tl__tag--r">{etClock(end)}</span>
            <span className="clip-tl__grip clip-tl__grip--l" role="slider" aria-label="Start" aria-valuemin={from} aria-valuemax={to} aria-valuenow={start}
              aria-valuetext={etClock(start)} tabIndex={0} onPointerDown={drag('start')} onKeyDown={nudge('start')} data-testid="clip-tl-start" />
            <span className="clip-tl__grip clip-tl__grip--r" role="slider" aria-label="End" aria-valuemin={from} aria-valuemax={to} aria-valuenow={end}
              aria-valuetext={etClock(end)} tabIndex={0} onPointerDown={drag('end')} onKeyDown={nudge('end')} data-testid="clip-tl-end" />
          </div>
          {playhead !== null ? <span className="clip-tl__playhead" style={{ left: `${scale.pct(playhead)}%` }} /> : null}
        </div>
      </div>
    </div>
  );
}
