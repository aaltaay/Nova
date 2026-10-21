/**
 * The words over Ahead's zone (ADR 065): "AHEAD · next 15 min", the "AI view, not data" tag and the exam tag side by
 * side (they wrap only when the zone is too narrow for both), the state sentences and a ▸ that opens the Ahead panel,
 * whose legend says what each mark means (nothing is laid over the candles or the volume for it); and "now HH:MM"
 * just left of the zone. Both sit on a solid backdrop in the DOM, over the canvas, so a level line drawn across the
 * pane's top passes behind them, never through their words. The primitive reports where the zone is (`place`), and
 * this moves the DOM itself so a scroll never renders React per frame. While the zone is not on screen, or too narrow
 * for the heading, the main sentence sits at the pane's top right instead -- some words are always showing while
 * Ahead is on.
 */
import { useEffect, useImperativeHandle, useRef, type Ref, type RefObject } from 'react';
import type { AheadScene } from './aheadSceneTypes';
import { openAheadSheet } from './aheadStore';
import type { ZoneLayout } from './AheadPrimitive';
import type { Rect } from './aheadCanvas';
import './ahead.css';

const HEADING_INSET_PX = 10;
const HEADING_TOP_PX = 6;
/** A heading narrower than this does not fit the zone. */
const HEADING_MIN_PX = 140;
/** The heading ends this far short of another word over the zone's top. */
const CAP_GAP_PX = 6;
/** "now HH:MM" ends this far left of the zone's edge. */
const NOW_GAP_PX = 4;

export interface HeadingHandle {
  /** Put the heading on the zone (null: no zone on screen); the time axis is this tall. */
  place: (z: ZoneLayout, axisHeight: number) => void;
}

const show = (el: HTMLElement | null, on: boolean) => {
  if (el) el.style.display = on ? '' : 'none';
};

/** Measures `el` when its words change (never per frame) and calls `done`. */
function useMeasured(el: RefObject<HTMLElement | null>, size: RefObject<{ w: number; h: number }>,
  done: () => void, key: unknown): void {
  useEffect(() => {
    const node = el.current;
    if (!node || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => {
      size.current = { w: node.offsetWidth, h: node.offsetHeight };
      done();
    });
    ro.observe(node);
    return () => ro.disconnect();
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
}

export function AheadHeading({ ref, symbol, scene, onSize }: {
  ref?: Ref<HeadingHandle>;
  symbol: string;
  scene: AheadScene;
  /** The heading's and "now"'s rectangles on the pane, for the close countdown to keep clear of; empty while hidden. */
  onSize: (rects: Rect[]) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const now = useRef<HTMLDivElement>(null);
  const note = useRef<HTMLDivElement>(null);
  const size = useRef({ w: 0, h: 0 });
  const nowSize = useRef({ w: 0, h: 0 });
  const fits = useRef<ZoneLayout>(null);
  const last = useRef<{ z: ZoneLayout; axis: number }>({ z: null, axis: 0 });

  /** "now" ends at the zone's left edge; it shows only while its whole chip is on the pane. */
  const nowLeft = (z: NonNullable<ZoneLayout>) => z.left - NOW_GAP_PX - nowSize.current.w;

  const report = () => {
    const rects: Rect[] = [];
    const z = fits.current;
    const { w, h } = size.current;
    if (z && w > 0) {
      rects.push({ left: z.left + HEADING_INSET_PX, top: HEADING_TOP_PX, right: z.left + HEADING_INSET_PX + w,
        bottom: HEADING_TOP_PX + h });
    }
    const zone = last.current.z;
    if (zone && nowSize.current.w > 0 && nowLeft(zone) >= 0) {
      rects.push({ left: nowLeft(zone), top: HEADING_TOP_PX, right: zone.left - NOW_GAP_PX,
        bottom: HEADING_TOP_PX + nowSize.current.h });
    }
    onSize(rects);
  };

  const place = (z: ZoneLayout, axisHeight: number) => {
    last.current = { z, axis: axisHeight };
    // Up to the zone's right, or short of the pane's other words over the zone's top (its backdrop never hides them).
    const end = z ? Math.min(z.right - HEADING_INSET_PX, (z.capRight ?? z.right) - CAP_GAP_PX) : 0;
    const room = z ? end - z.left - HEADING_INSET_PX : 0;
    const fit = z && room >= HEADING_MIN_PX ? z : null;
    fits.current = fit;
    show(box.current, fit !== null);
    show(note.current, fit === null);
    if (fit && box.current) {
      box.current.style.transform = `translate(${Math.round(fit.left + HEADING_INSET_PX)}px, ${HEADING_TOP_PX}px)`;
      box.current.style.maxWidth = `${room}px`;
    }
    const nowOn = z !== null && nowLeft(z) >= 0;
    show(now.current, nowOn);
    if (z && nowOn && now.current) {
      now.current.style.transform = `translate(${Math.round(nowLeft(z))}px, ${HEADING_TOP_PX}px)`;
    }
    report();
  };

  useImperativeHandle(ref, () => ({ place }));

  // A zone that mounted after the last move takes its place at once.
  const hasZone = scene.zone !== null;
  useEffect(() => {
    place(last.current.z, last.current.axis);
  }, [hasZone]); // eslint-disable-line react-hooks/exhaustive-deps

  // The words' sizes change with the words only, so the browser measures them when they do, never per frame.
  useMeasured(box, size, report, hasZone);
  useMeasured(now, nowSize, () => place(last.current.z, last.current.axis), hasZone);

  const open = () => openAheadSheet(symbol);
  const words = scene.words;
  const z = scene.zone;
  return (
    <>
      {z && (
        <div ref={now} className="ahead-now" style={{ display: 'none' }} data-testid="ahead-now">{z.nowText}</div>
      )}
      {z && (
        <div ref={box} className="ahead-heading" style={{ display: 'none' }} data-testid="ahead-heading">
          <div className="ahead-heading__row">
            <span className="ahead-heading__title">{z.title}</span>
            <button type="button" className="ahead-heading__open" onClick={open} aria-label="Open the Ahead panel"
              data-testid="ahead-open-sheet">▸</button>
          </div>
          <div className="ahead-heading__tags" data-testid="ahead-tags">
            {z.tags.map(t => (
              <span key={t.text} className="ahead-tag" style={{ color: t.fg, background: t.bg }}>{t.text}</span>
            ))}
          </div>
          {words.map((w, i) => (
            <div key={w} className={i === 0 ? 'ahead-heading__word' : 'ahead-heading__word ahead-heading__word--more'}>
              {w}
            </div>
          ))}
        </div>
      )}
      <div ref={note} className="ahead-pane-note" data-testid="ahead-pane-note">
        <span>{words[0] ?? z?.title ?? ''}</span>
        <button type="button" className="ahead-heading__open" onClick={open} aria-label="Open the Ahead panel"
          data-testid="ahead-open-sheet-note">▸</button>
      </div>
    </>
  );
}
