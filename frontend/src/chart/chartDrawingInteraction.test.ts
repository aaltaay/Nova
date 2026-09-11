import { describe, expect, it } from 'vitest';
import { chartInteractionForTool } from './chartDrawingInteraction';

describe('chartInteractionForTool', () => {
  it('keeps pressed-mouse pan on when no drawing tool is armed', () => {
    const opts = chartInteractionForTool(null);
    expect(opts.handleScroll.pressedMouseMove).toBe(true);
    expect(opts.handleScale.axisPressedMouseMove).toBe(true);
    expect(opts.handleScroll.mouseWheel).toBe(true);
  });

  it.each(['TrendLine', 'ExtendedLine', 'Ray'])(
    'disables pan/scale drag and kinetic fling while %s is armed',
    (tool) => {
      const opts = chartInteractionForTool(tool);
      expect(opts.handleScroll.pressedMouseMove).toBe(false);
      expect(opts.handleScroll.horzTouchDrag).toBe(false);
      expect(opts.handleScroll.vertTouchDrag).toBe(false);
      expect(opts.handleScale.axisPressedMouseMove).toBe(false);
      expect(opts.kineticScroll.mouse).toBe(false);
      expect(opts.kineticScroll.touch).toBe(false);
      expect(opts.handleScroll.mouseWheel).toBe(true);
    },
  );
});
