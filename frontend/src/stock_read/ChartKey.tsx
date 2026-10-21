/**
 * The Key chip on a Trader chart pane: point at it (or press it) and a small card lists what each colour
 * on that pane means (`paneKeyRows.chartKey`). It takes the pointer only over the chip and the card, so the chart keeps
 * every gesture elsewhere. The card fits its pane: as it opens it is measured against the pane (the positioned box the
 * pane's corner sits in) and scrolls inside that height, so a long Key never runs off the pane over the candles.
 */
import { useRef, useState, type PointerEvent } from 'react';
import { KEY_CARD_MIN_PX, KEY_CARD_PANE_MARGIN_PX } from './constants';
import type { KeyRow, KeySection } from './paneKeyRows';

/** The card's tallest: from under the chip to just above the pane's bottom, never under the floor. Null when the pane
 * has no height yet (not laid out): the stylesheet's own cap holds. Pure. */
export function keyCardMaxHeight(chipBottom: number, pane: { top: number; bottom: number }): number | null {
  if (pane.bottom - pane.top <= 0) return null;
  return Math.max(KEY_CARD_MIN_PX, Math.floor(pane.bottom - chipBottom - KEY_CARD_PANE_MARGIN_PX));
}

/** The pane a Key chip sits on: the positioned box its corner (`.sr-pane-top` / `.sr-legend`) is placed in. */
function paneOf(el: HTMLElement): Element | null {
  const corner = el.closest('.sr-pane-top, .sr-legend') as HTMLElement | null;
  return corner ? corner.offsetParent ?? corner.parentElement : el.parentElement;
}

function Swatch({ row }: { row: KeyRow }) {
  if (row.swatch === 'band') {
    return <i className="sr-key__swatch sr-key__swatch--band" style={{ background: row.fill ?? row.color }} aria-hidden="true" />;
  }
  if (row.swatch === 'hatch') {
    const ground = row.fill ?? 'transparent';
    return (
      <i className="sr-key__swatch sr-key__swatch--band" aria-hidden="true"
        style={{ background: `repeating-linear-gradient(-45deg, ${ground} 0 6px, ${row.color} 6px 9px)` }} />
    );
  }
  if (row.swatch === 'paths') {
    return (
      <svg className="sr-key__swatch sr-key__swatch--paths" viewBox="0 0 22 12" aria-hidden="true">
        <polyline points="1,6 7,4 13,7 21,2" fill="none" stroke={row.color} strokeOpacity={0.8} />
        <polyline points="1,6 7,8 13,6 21,10" fill="none" stroke={row.color} strokeOpacity={0.5} />
      </svg>
    );
  }
  if (row.swatch === 'box') {
    return (
      <i className="sr-key__swatch sr-key__swatch--box" style={{ background: row.fill, borderColor: row.color }} aria-hidden="true" />
    );
  }
  if (row.swatch === 'ring') {
    return (
      <i className="sr-key__swatch sr-key__swatch--ring" style={{ background: row.fill, borderColor: row.color }} aria-hidden="true" />
    );
  }
  if (row.swatch === 'up') {
    return <i className="sr-key__swatch sr-key__swatch--up" style={{ borderBottomColor: row.color }} aria-hidden="true" />;
  }
  if (row.swatch === 'rise' || row.swatch === 'fall') {
    return (
      <i
        className={`sr-key__swatch sr-key__swatch--line sr-key__swatch--${row.swatch}`}
        style={{ borderTop: `2px solid ${row.color}` }}
        aria-hidden="true"
      />
    );
  }
  const style = row.swatch === 'line' ? 'solid' : row.swatch === 'dash' ? 'dashed' : 'dotted';
  return <i className="sr-key__swatch sr-key__swatch--line" style={{ borderTop: `2px ${style} ${row.color}` }} aria-hidden="true" />;
}

const stop = (e: PointerEvent) => e.stopPropagation();

export function ChartKey({ sections, testId }: { sections: KeySection[]; testId: string }) {
  const [pinned, setPinned] = useState(false);
  const [maxHeight, setMaxHeight] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);
  // Measured each time the card may open (pointed at, focused, pressed): the pane may have been resized since.
  const fit = () => {
    const el = ref.current;
    const pane = el ? paneOf(el) : null;
    if (!el || !pane) return;
    const h = keyCardMaxHeight(el.getBoundingClientRect().bottom, pane.getBoundingClientRect());
    setMaxHeight(was => (was === h ? was : h));
  };
  if (sections.length === 0) return null;
  return (
    <div ref={ref} className={`sr-key${pinned ? ' sr-key--open' : ''}`} onPointerDown={stop} onPointerEnter={fit}
      onFocus={fit} data-testid={testId}>
      <button
        type="button"
        className="sr-key__chip"
        aria-expanded={pinned}
        onClick={() => {
          fit();
          setPinned(p => !p);
        }}
        data-testid={`${testId}-chip`}
      >
        ⓘ Key
      </button>
      <div className="sr-key__card" role="tooltip" data-testid={`${testId}-card`}
        style={maxHeight !== null ? { maxHeight: `${maxHeight}px` } : undefined}>
        {sections.map(s => (
          <div key={s.title} className="sr-key__section">
            <div className="sr-key__title">{s.title}</div>
            {s.rows.map(r => (
              <div key={r.label} className="sr-key__row">
                <Swatch row={r} />
                <span className="sr-key__label">{r.label}</span>
                <span className="sr-key__text">{r.text}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** A pane's Key with no read behind it: only the sections another layer still draws (Ahead's zone while the read
 * loads, or on a Sim rewind before the read was made), so nothing on the pane goes unexplained. Nothing without them. */
export function PaneKeyOnly({ sections, testId }: { sections: KeySection[]; testId: string }) {
  if (sections.length === 0) return null;
  return (
    <div className="sr-pane-top" data-testid={`${testId}-only`}>
      <ChartKey sections={sections} testId={testId} />
    </div>
  );
}
