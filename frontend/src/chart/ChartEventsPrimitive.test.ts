import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { CHART_EVENT_BOTTOM_GAP_PX, CHART_EVENT_RADIUS_PX, CHART_EVENT_STACK_GAP_PX } from './chartEventConstants';
import { CHART_EVENT_HOVER_PREFIX, ChartEventsPrimitive, layoutEventMarks, markAt, type EventMark } from './ChartEventsPrimitive';

const mark = (id: string, time: string, letter = 'E'): EventMark => ({ id, time: time as Time, letter, color: '#fff' });
const xs: Record<string, number | null> = { '2026-03-12': 100, '2026-06-29': 240, '2026-09-01': null };

describe('layoutEventMarks', () => {
  it('sits each mark on the pane bottom under its candle and stacks a second one above the first', () => {
    const px = layoutEventMarks([mark('e', '2026-06-29'), mark('m', '2026-06-29', 'M'), mark('f', '2026-03-12')],
      (m) => xs[String(m.time)] ?? null, 300);
    const bottom = 300 - CHART_EVENT_BOTTOM_GAP_PX - CHART_EVENT_RADIUS_PX;
    expect(px.map((p) => [p.id, p.x, p.y])).toEqual([
      ['e', 240, bottom],
      ['m', 240, bottom - 2 * CHART_EVENT_RADIUS_PX - CHART_EVENT_STACK_GAP_PX],
      ['f', 100, bottom],
    ]);
  });

  it('leaves out a mark whose candle is off the time scale', () => {
    expect(layoutEventMarks([mark('x', '2026-09-01')], (m) => xs[String(m.time)] ?? null, 300)).toEqual([]);
  });
});

describe('hit testing', () => {
  it('finds the mark under the pointer and reports it with its hover id', () => {
    const primitive = new ChartEventsPrimitive();
    primitive.px = layoutEventMarks([mark('split:2026-06-29', '2026-06-29', 'M')], () => 240, 300);
    const { y } = primitive.px[0];
    expect(markAt(primitive.px, 243, y)?.id).toBe('split:2026-06-29');
    expect(markAt(primitive.px, 240, y - 40)).toBeNull();
    expect(primitive.hitTest(240, y)).toEqual({
      externalId: `${CHART_EVENT_HOVER_PREFIX}split:2026-06-29`, zOrder: 'top', cursorStyle: 'pointer',
    });
    expect(primitive.hitTest(10, 10)).toBeNull();
  });
});
