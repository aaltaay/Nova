/** The legend of Ahead's zone (ADR 065), at the top of the Ahead panel: what each mark on the chart means, with a
 * swatch drawn like the mark -- a dashed line for Nova's lines, the band's two strengths, the soft cloud, a story path
 * in its three stages and its marks, the ghost volume bar's outline and the hatch. Kept off the chart, so it never covers a candle or a volume bar. */
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import type { SceneLegendRow } from './aheadSceneTypes';

/** The swatch drawn like its mark: the cloud as many faint lines, a story path grey then coloured then faded, the
 * story marks as the chart draws them (on scope All, the filled diamond where a path first reaches a wall). */
function Swatch({ kind, cases }: { kind: SceneLegendRow['swatch']; cases?: boolean }) {
  if (kind === 'paths') {
    return (
      <svg className="ahead-swatch ahead-swatch--svg" viewBox="0 0 26 12" aria-hidden="true">
        {['1,6 8,4 15,7 25,2', '1,6 8,8 15,6 25,10', '1,6 8,5 15,5 25,6', '1,6 8,7 15,9 25,8'].map(pts => (
          <polyline key={pts} points={pts} fill="none" stroke={AHEAD_COLORS.path} strokeOpacity={0.35} />
        ))}
      </svg>
    );
  }
  if (kind === 'story') {
    const on = cases ? AHEAD_COLORS.wallAbove : AHEAD_COLORS.target;
    return (
      <svg className="ahead-swatch ahead-swatch--svg" viewBox="0 0 26 12" aria-hidden="true">
        <polyline points="1,8 9,9" fill="none" stroke={AHEAD_COLORS.muted} strokeOpacity={0.6} strokeWidth={1.6} />
        <polyline points="9,9 18,3" fill="none" stroke={on} strokeWidth={1.6} />
        <polyline points="18,3 25,5" fill="none" stroke={on} strokeOpacity={0.25} strokeWidth={1.6} />
      </svg>
    );
  }
  if (kind === 'marks') {
    if (cases) {
      return (
        <svg className="ahead-swatch ahead-swatch--svg" viewBox="0 0 26 12" aria-hidden="true">
          <polygon points="13,1.5 17.5,6 13,10.5 8.5,6" fill={AHEAD_COLORS.wallAbove} data-testid="ahead-swatch-diamond" />
        </svg>
      );
    }
    return (
      <svg className="ahead-swatch ahead-swatch--svg" viewBox="0 0 26 12" aria-hidden="true">
        <circle cx={4} cy={6} r={3} fill={AHEAD_COLORS.trigger} />
        <polyline points="10,6 12.5,9 16,3" fill="none" stroke={AHEAD_COLORS.target} strokeWidth={1.6} />
        <path d="M19.5 3 L24.5 9 M24.5 3 L19.5 9" stroke={AHEAD_COLORS.stop} strokeWidth={1.6} />
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
          <Swatch kind={r.swatch} cases={r.cases} />
          <span>{r.text}</span>
        </div>
      ))}
    </div>
  );
}
