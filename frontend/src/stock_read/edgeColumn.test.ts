import { describe, expect, it } from 'vitest';
import {
  COLUMN_MAX_SHIFT_PX,
  COLUMN_MAX_TAGS,
  COLUMN_STEP,
  centreRuns,
  layoutColumn,
  type ColumnItem,
} from './edgeColumn';
import { columnItems } from './sceneRender';
import { LABEL_H } from './sceneLabels';

function item(y: number, over: Partial<ColumnItem> = {}): ColumnItem {
  return { y, text: `w${y}`, color: '#ffffff', style: 'plain', priority: 60, hoverId: null, offText: null, ...over };
}

function placed(layout: ReturnType<typeof layoutColumn>, i: number): number | undefined {
  return layout.slots.find(s => s.item === i)?.y;
}

describe('the edge column (operator report 2026-09-30: "everything is getting on top of each other")', () => {
  it('leaves a word on its line when nothing is near it', () => {
    const layout = layoutColumn([item(100), item(200)], 400);
    expect(placed(layout, 0)).toBe(100);
    expect(placed(layout, 1)).toBe(200);
    expect(layout.dropped).toEqual([]);
  });

  it('centres a crowd on its lines, in their order, one row apart', () => {
    // A level, the 9 EMA and VWAP within four pixels: three rows around their middle, never crossing.
    const items = [item(204, { text: 'VWAP' }), item(200, { text: '$5.00 · double top' }), item(202, { text: '9 EMA' })];
    const layout = layoutColumn(items, 400);
    const ys = [placed(layout, 1)!, placed(layout, 2)!, placed(layout, 0)!];
    expect(ys[1] - ys[0]).toBe(COLUMN_STEP);
    expect(ys[2] - ys[1]).toBe(COLUMN_STEP);
    expect((ys[0] + ys[1] + ys[2]) / 3).toBeCloseTo(202, 5);
  });

  it('keeps every word inside the pane, pushing a crowd at the bottom edge back up', () => {
    const layout = layoutColumn([item(396), item(398), item(399)], 400);
    for (const s of layout.slots) {
      expect(s.y + LABEL_H / 2).toBeLessThanOrEqual(400);
      expect(s.y - LABEL_H / 2).toBeGreaterThanOrEqual(0);
    }
  });

  it('drops the least important word of a crowd that cannot sit near its lines, and reports it', () => {
    // Ten words on one price: only the ones within reach of the line keep a label.
    const items = Array.from({ length: 10 }, (_, i) => item(200, { priority: i === 3 ? 100 : 50 + i, hoverId: `h${i}` }));
    const layout = layoutColumn(items, 600);
    for (const s of layout.slots) expect(Math.abs(s.y - 200)).toBeLessThanOrEqual(COLUMN_MAX_SHIFT_PX);
    expect(layout.slots.some(s => s.item === 3)).toBe(true); // the most important stays
    expect(layout.dropped).toContain(0); // the least important goes first
    expect(layout.slots.length + layout.dropped.length).toBe(10);
  });

  it('drops words when the pane is too short for them all, the least important first', () => {
    const items = [item(10, { priority: 40 }), item(20, { priority: 90 }), item(30, { priority: 60 })];
    const layout = layoutColumn(items, 2 * COLUMN_STEP + 2); // room for two rows
    expect(layout.dropped).toEqual([0]);
  });

  it('stacks tags for prices out of view under the corner chips and at the bottom, in price order', () => {
    const items = [
      item(-50, { offText: 'HOD 9.79', priority: 40 }),
      item(-10, { offText: '200 EMA 7.31', priority: 40 }),
      item(450, { offText: 'LOD 3.25', priority: 40 }),
      item(-5), // out of view with nothing to say: no tag
    ];
    const layout = layoutColumn(items, 400, 30);
    const hod = layout.slots.find(s => s.item === 0)!;
    const ema = layout.slots.find(s => s.item === 1)!;
    expect(hod.text).toBe('↑ HOD 9.79');
    expect(hod.y - LABEL_H / 2).toBeGreaterThanOrEqual(30); // under the chips
    expect(ema.y).toBe(hod.y + COLUMN_STEP); // the higher price on top
    expect(hod.lineY).toBeNull();
    expect(layout.slots.find(s => s.item === 2)!.text).toBe('↓ LOD 3.25');
    expect(layout.slots.some(s => s.item === 3)).toBe(false);
  });

  it(`keeps at most ${COLUMN_MAX_TAGS} tags at an end, the most important first`, () => {
    const items = [10, 20, 30, 40, 50].map((d, i) => item(-d, { offText: `t${i}`, priority: i === 4 ? 90 : 40 }));
    const layout = layoutColumn(items, 400);
    expect(layout.slots).toHaveLength(COLUMN_MAX_TAGS);
    expect(layout.slots.some(s => s.item === 4)).toBe(true);
  });

  it('never covers room something else holds (the position tag)', () => {
    const items = [item(195), item(200), item(205)];
    const layout = layoutColumn(items, 400, 0, [{ top: 190, bottom: 210 }]);
    for (const s of layout.slots) {
      const overlaps = s.y + LABEL_H / 2 > 190 && s.y - LABEL_H / 2 < 210;
      expect(overlaps).toBe(false);
    }
    expect(layout.slots).toHaveLength(3);
  });

  it('centreRuns merges only the runs that touch', () => {
    const { at, run } = centreRuns([100, 102, 300], 0, 400);
    expect(run).toEqual([0, 0, 1]);
    expect(at[2]).toBe(300);
    expect(at[1] - at[0]).toBe(COLUMN_STEP);
  });
});

describe('the column\'s words', () => {
  const series = {} as never;
  it("are the levels' names, the lines' tags and a tag for each price out of view", () => {
    const items = columnItems({
      levels: [
        { y: 50, y1: 50, y2: 50, l: { lo: 5, hi: 5, price: 5, color: '#f59e0b', dash: [], width: 1, label: '$5.00 · double top',
          hoverId: 'level:x' } },
        { y: 60, y1: 60, y2: 60, l: { lo: 4, hi: 4, price: 4, color: '#f59e0b', dash: [], width: 1, label: null, hoverId: null } },
      ],
      words: [
        { y: 70, value: 7.312, w: { id: 'ema200', text: '200 EMA', color: '#A855F7', priority: 50, price: null, series,
          valueWhenOff: true } },
        { y: 80, value: 5.16, w: { id: 'vwap', text: 'VWAP $5.16', color: '#F97316', priority: 80, price: null, series,
          valueWhenOff: false } },
      ],
      tags: [
        { y: -20, t: { price: 9.79, label: 'HOD 9.79', color: '#fff' } },
        { y: 30, t: { price: 6, label: 'in view', color: '#fff' } },
        { y: -40, t: { price: 6.1, label: 'VWAP 6.10', color: '#fff', id: 'vwap' } },
      ],
    }, 400);
    expect(items.map(i => i.text)).toEqual(['$5.00 · double top', '200 EMA', 'VWAP $5.16', 'HOD 9.79']);
    expect(items[0]).toMatchObject({ style: 'plain', hoverId: 'level:x', offText: null });
    expect(items[1]).toMatchObject({ style: 'filled', offText: '200 EMA 7.31' });
    expect(items[2].offText).toBe('VWAP $5.16');
    expect(items[3]).toMatchObject({ offText: 'HOD 9.79', y: -20 });
  });
});
