/** The legend of Ahead's zone (ADR 065), at the top of the Ahead panel: what each mark on the chart means, with a
 * swatch drawn like the mark -- a dashed line for Nova's lines, the band's two strengths, a few paths, the ghost volume
 * bar's outline and the hatch. Kept off the chart, so it never covers a candle or a volume bar. */
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import type { SceneLegendRow } from './aheadSceneTypes';

function Swatch({ kind }: { kind: SceneLegendRow['swatch'] }) {
  if (kind === 'paths') {
    return (
      <svg className="ahead-swatch ahead-swatch--svg" viewBox="0 0 26 12" aria-hidden="true">
        <polyline points="1,6 8,4 15,7 25,2" fill="none" stroke={AHEAD_COLORS.path} strokeOpacity={0.8} />
        <polyline points="1,6 8,8 15,6 25,10" fill="none" stroke={AHEAD_COLORS.path} strokeOpacity={0.5} />
      </svg>
    );
  }
  return <i className={`ahead-swatch ahead-swatch--${kind}`} aria-hidden="true" />;
}

export function LegendRows({ rows }: { rows: SceneLegendRow[] }) {
  return (
    <div className="ahead-legend" data-testid="ahead-legend">
      <div className="ahead-legend__title">{AHEAD_WORDS.legendTitle}</div>
      {rows.map(r => (
        <div key={r.swatch} className="ahead-legend__row" data-testid={`ahead-legend-${r.swatch}`}>
          <Swatch kind={r.swatch} />
          <span>{r.text}</span>
        </div>
      ))}
    </div>
  );
}
