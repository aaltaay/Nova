/**
 * The Key chip on a Trader chart pane: point at it (or press it) and a small card lists what each colour
 * on that pane means (`paneKeyRows.chartKey`). It takes the pointer only over the chip and the card, so the chart keeps
 * every gesture elsewhere.
 */
import { useState, type PointerEvent } from 'react';
import type { KeyRow, KeySection } from './paneKeyRows';

function Swatch({ row }: { row: KeyRow }) {
  if (row.swatch === 'band') {
    return <i className="sr-key__swatch sr-key__swatch--band" style={{ background: row.color }} aria-hidden="true" />;
  }
  if (row.swatch === 'box') {
    return (
      <i className="sr-key__swatch sr-key__swatch--box" style={{ background: row.fill, borderColor: row.color }} aria-hidden="true" />
    );
  }
  const style = row.swatch === 'line' ? 'solid' : row.swatch === 'dash' ? 'dashed' : 'dotted';
  return <i className="sr-key__swatch sr-key__swatch--line" style={{ borderTop: `2px ${style} ${row.color}` }} aria-hidden="true" />;
}

const stop = (e: PointerEvent) => e.stopPropagation();

export function ChartKey({ sections, testId }: { sections: KeySection[]; testId: string }) {
  const [pinned, setPinned] = useState(false);
  if (sections.length === 0) return null;
  return (
    <div className={`sr-key${pinned ? ' sr-key--open' : ''}`} onPointerDown={stop} data-testid={testId}>
      <button
        type="button"
        className="sr-key__chip"
        aria-expanded={pinned}
        onClick={() => setPinned(p => !p)}
        data-testid={`${testId}-chip`}
      >
        ⓘ Key
      </button>
      <div className="sr-key__card" role="tooltip" data-testid={`${testId}-card`}>
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
