/**
 * The words over Ahead's zone (ADR 061): "AHEAD · next 15 min", the "AI view, not data" tag and the exam tag, the
 * state sentences, a ▸ that opens the Ahead panel, and the legend strip at the pane's bottom left. The primitive
 * reports where the zone is (`place`), and this moves the DOM itself so a scroll never renders React per frame.
 * While the zone is not on screen, or too narrow for the heading, the main sentence sits at the pane's top right
 * instead -- some words are always showing while Ahead is on.
 */
import { useEffect, useImperativeHandle, useRef, type Ref } from 'react';
import type { AheadScene } from './aheadSceneTypes';
import { openAheadSheet } from './aheadStore';
import type { ZoneLayout } from './AheadPrimitive';
import type { Rect } from './aheadCanvas';
import './ahead.css';

const HEADING_INSET_PX = 10;
const HEADING_TOP_PX = 6;
/** A heading narrower than this does not fit the zone; a legend narrower than this is left out. */
const HEADING_MIN_PX = 140;
const LEGEND_MIN_PX = 180;

export interface HeadingHandle {
  /** Put the heading on the zone (null: no zone on screen) and the legend above a time axis this tall. */
  place: (z: ZoneLayout, axisHeight: number) => void;
}

const show = (el: HTMLElement | null, on: boolean) => {
  if (el) el.style.display = on ? '' : 'none';
};

export function AheadHeading({ ref, symbol, scene, onSize }: {
  ref?: Ref<HeadingHandle>;
  symbol: string;
  scene: AheadScene;
  /** The heading's rectangle on the pane, for the close countdown to keep clear of; null while hidden. */
  onSize: (rect: Rect | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const note = useRef<HTMLDivElement>(null);
  const legend = useRef<HTMLDivElement>(null);
  const size = useRef({ w: 0, h: 0 });
  const fits = useRef<ZoneLayout>(null);
  const last = useRef<{ z: ZoneLayout; axis: number }>({ z: null, axis: 0 });

  const report = () => {
    const z = fits.current;
    const { w, h } = size.current;
    onSize(z && w > 0 ? { left: z.left + HEADING_INSET_PX, top: HEADING_TOP_PX, right: z.left + HEADING_INSET_PX + w,
      bottom: HEADING_TOP_PX + h } : null);
  };

  const place = (z: ZoneLayout, axisHeight: number) => {
    last.current = { z, axis: axisHeight };
    const room = z ? z.right - z.left - 2 * HEADING_INSET_PX : 0;
    const fit = z && room >= HEADING_MIN_PX ? z : null;
    fits.current = fit;
    show(box.current, fit !== null);
    show(note.current, fit === null);
    if (fit && box.current) {
      box.current.style.transform = `translate(${Math.round(fit.left + HEADING_INSET_PX)}px, ${HEADING_TOP_PX}px)`;
      box.current.style.maxWidth = `${room}px`;
    }
    const lg = legend.current;
    if (lg) {
      const lroom = z ? z.left - 2 * HEADING_INSET_PX : 0;
      show(lg, lroom >= LEGEND_MIN_PX);
      lg.style.maxWidth = `${Math.max(0, lroom)}px`;
      lg.style.bottom = `${axisHeight + 4}px`;
    }
    report();
  };

  useImperativeHandle(ref, () => ({ place }));

  // A part that mounted after the last move (a zone, a legend that came) takes its place at once.
  const hasZone = scene.zone !== null;
  const hasLegend = scene.legend !== null;
  useEffect(() => {
    place(last.current.z, last.current.axis);
  }, [hasZone, hasLegend]); // eslint-disable-line react-hooks/exhaustive-deps

  // The heading's size changes with its words only, so the browser measures it when they do, never per frame.
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => {
      size.current = { w: el.offsetWidth, h: el.offsetHeight };
      report();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasZone]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = () => openAheadSheet(symbol);
  const words = scene.words;
  const z = scene.zone;
  return (
    <>
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
      {scene.legend && (
        <div ref={legend} className="ahead-legend" style={{ display: 'none' }} data-testid="ahead-legend">
          {scene.legend}
        </div>
      )}
    </>
  );
}
