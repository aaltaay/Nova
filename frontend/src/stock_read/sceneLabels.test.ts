import { describe, expect, it } from 'vitest';
import { labelForms, labelRect, placeLabels, type LabelAsk } from './sceneLabels';

/** Ten pixels a character, no padding: widths a reader can check by eye. */
const measure = (text: string) => text.length * 10;
const PANE = 1000;

function ask(forms: string[], x: number, y: number, rank = 0, fixed = false): LabelAsk {
  return { forms, x, y, rank, fixed };
}

describe('the forms a label may take', () => {
  const shrink = { short: '✕ topping tail ↘', icon: '✕↘', rank: 1 };

  it('starts from the whole label in full, from a few words in compact', () => {
    const whole = '✕ topping tail · ↘ then broke down';
    expect(labelForms(whole, shrink, 'full')).toEqual([whole, '✕ topping tail ↘', '✕↘']);
    expect(labelForms(whole, shrink, 'compact')).toEqual(['✕ topping tail ↘', '✕↘']);
  });

  it('keeps a live label whole in either, and a leg says nothing in compact', () => {
    expect(labelForms('PULLBACK 3', undefined, 'compact')).toEqual(['PULLBACK 3']);
    expect(labelForms('POLE +15.3%', { short: null, icon: null, rank: 0 }, 'compact')).toEqual([]);
    expect(labelForms('POLE +15.3%', { short: null, icon: null, rank: 0 }, 'full')).toEqual(['POLE +15.3%']);
    expect(labelForms('✓', { short: '✓', icon: '✓', rank: 0 }, 'full')).toEqual(['✓']);
  });
});

describe('where the labels go', () => {
  it('gives the room to the newest first, and an older one shrinks, then steps aside', () => {
    const older = ask(['older whole', 'older', 'o'], 100, 50, 1);
    const newer = ask(['newer whole', 'newer'], 100, 50, 2);
    // `newer` takes its whole form; `older` finds every form in its way and says nothing.
    expect(placeLabels([older, newer], measure, PANE).map(l => l.text)).toEqual(['newer whole']);
    // Right after `newer whole` (100 + 110 = 210) with a level's words at 240, only `older`'s icon fits.
    const beside = ask(['older whole', 'older', 'o'], 211, 50, 1);
    const level = { left: 240, top: 40, right: 400, bottom: 60 };
    expect(placeLabels([beside, newer], measure, PANE, [level]).map(l => l.text)).toEqual(['o', 'newer whole']);
    expect(placeLabels([beside, newer], measure, PANE).map(l => l.text)).toEqual(['older whole', 'newer whole']);
  });

  it('keeps a label on its own row whole', () => {
    const a = ask(['first whole', 'a'], 100, 50, 2);
    const b = ask(['second whole', 'b'], 100, 65, 1);   // 15 px lower: a 14 px label and a pixel's gap
    expect(placeLabels([a, b], measure, PANE).map(l => l.text)).toEqual(['first whole', 'second whole']);
    const touching = ask(['second whole', 'b'], 100, 64, 1);
    expect(placeLabels([a, touching], measure, PANE).map(l => [l.text, l.left])).toEqual([['first whole', 100]]);
  });

  it('places a live label where it is whatever it runs into, and a past one around it', () => {
    const live = ask(['PULLBACK 3'], 100, 50, 0, true);
    const past = ask(['✕ topping tail', '✕'], 100, 50, 9e9);
    const obstacle = { left: 0, top: 80, right: 400, bottom: 94 };
    const underLevel = ask(['✕ ran too long', '✕'], 100, 87, 9e9);
    const placed = placeLabels([past, live, underLevel], measure, PANE, [obstacle]);
    expect(placed.map(l => l.text)).toEqual(['PULLBACK 3']);
    const twoLive = placeLabels([live, { ...live, forms: ['POLE +6%'] }], measure, PANE);
    expect(twoLive.map(l => l.text)).toEqual(['PULLBACK 3', 'POLE +6%']);
  });

  it('keeps a label inside the pane when its box starts past an edge', () => {
    expect(labelRect(-40, 50, 100, 'left', PANE).left).toBe(2);
    expect(labelRect(950, 50, 100, 'left', PANE).left).toBe(898);
    expect(labelRect(990, 50, 100, 'right', PANE)).toMatchObject({ left: 890, right: 990, top: 43, bottom: 57 });
    const [cut] = placeLabels([ask(['✕ topping tail'], -60, 50)], measure, PANE);
    expect(cut.left).toBe(2);
  });

  it('returns what it placed in the order the boxes are drawn', () => {
    const asks = [ask(['a'], 0, 10, 1), ask(['b'], 0, 40, 3), ask(['c'], 0, 70, 2)];
    expect(placeLabels(asks, measure, PANE).map(l => [l.ask, l.text])).toEqual([[0, 'a'], [1, 'b'], [2, 'c']]);
  });
});
