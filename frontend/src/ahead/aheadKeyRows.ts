/** Ahead's section in the desk's chart Key (ADR 065): while Ahead draws on a pane, the Key button on that pane lists
 * what each mark in the zone means with the same swatches as the Ahead panel's legend -- and the marks the legend
 * leaves to the chart: the meet ring, the wall chips and their "if it breaks" line -- so the zone is explained with the
 * panel closed. Each row is one label and words that do not repeat it (`AHEAD_KEY_ROWS`). Pure. */
import type { KeyRow, KeySection } from '../stock_read';
import { AHEAD_COLORS, AHEAD_KEY_ROWS, AHEAD_KEY_TITLE } from './aheadConstants';
import type { AheadScene, SceneLegendRow } from './aheadSceneTypes';

const K = AHEAD_KEY_ROWS;

function legendRow(r: SceneLegendRow): KeyRow {
  switch (r.swatch) {
    case 'dash': return { swatch: 'dash', color: AHEAD_COLORS.resistance, ...K.dash };
    case 'band': return { swatch: 'band', color: AHEAD_COLORS.ai, fill: AHEAD_COLORS.keyBand, ...K.band };
    case 'paths': return { swatch: 'paths', color: AHEAD_COLORS.path, label: K.paths.label, text: K.paths.text(r.n ?? 0) };
    case 'box': return { swatch: 'box', color: AHEAD_COLORS.ai, fill: AHEAD_COLORS.keyBoxFill, ...K.box };
    case 'hatch': return { swatch: 'hatch', color: AHEAD_COLORS.keyHatchStripe, fill: AHEAD_COLORS.hatch, ...K.hatch };
  }
}

/** The Key's Ahead section from the scene: its legend, then the meet ring, the wall chips and the break line while
 * each is drawn. Null when the scene draws no zone. */
export function aheadKeySection(scene: Pick<AheadScene, 'legend' | 'meet' | 'chips'>, on: boolean): KeySection | null {
  if (!on || scene.legend.length === 0) return null;
  const rows = scene.legend.map(legendRow);
  // The ring goes right after Nova's lines (the dash row), whose meet it marks.
  if (scene.meet?.inZone) {
    rows.splice(rows.findIndex(r => r.swatch === 'dash') + 1, 0,
      { swatch: 'ring', color: AHEAD_COLORS.meetRing, ...K.ring });
  }
  const walls = scene.chips.filter(c => c.role === 'wall');
  if (walls.length > 0) rows.push({ swatch: 'up', color: AHEAD_COLORS.wallAbove, ...K.wallFirst });
  if (walls.some(c => c.sub)) rows.push({ swatch: 'line', color: AHEAD_COLORS.wallAbove, ...K.breaks });
  return { title: AHEAD_KEY_TITLE, rows };
}
