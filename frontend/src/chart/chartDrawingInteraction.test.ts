/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import {
  applyChartHostInteraction,
  chartInteractionForTool,
  chartPanLocked,
} from './chartDrawingInteraction';

describe('chartInteractionForTool', () => {
  it('keeps pressed-mouse pan on when idle and not editing a handle', () => {
    const opts = chartInteractionForTool(null);
    expect(opts.handleScroll.pressedMouseMove).toBe(true);
    expect(opts.handleScale.axisPressedMouseMove).toBe(true);
    expect(opts.handleScroll.mouseWheel).toBe(true);
  });

  it('disables pan while a selected handle is being dragged, even if no tool is armed', () => {
    const opts = chartInteractionForTool(null, true);
    expect(opts.handleScroll.pressedMouseMove).toBe(false);
    expect(opts.handleScroll.horzTouchDrag).toBe(false);
    expect(opts.handleScale.axisPressedMouseMove).toBe(false);
    expect(opts.kineticScroll.mouse).toBe(false);
    expect(opts.handleScroll.mouseWheel).toBe(true);
  });

  it('restores pan when idle after handle edit ends', () => {
    expect(chartInteractionForTool(null, false).handleScroll.pressedMouseMove).toBe(true);
    expect(chartPanLocked(null, false)).toBe(false);
    expect(chartPanLocked(null, true)).toBe(true);
    expect(chartPanLocked('TrendLine', false)).toBe(true);
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

describe('applyChartHostInteraction', () => {
  it('stamps pan-lock and handle-edit flags on the chart host', () => {
    const host = document.createElement('div');
    const applyOptions = vi.fn();
    applyChartHostInteraction(host, { applyOptions }, null, true);
    expect(host.dataset.chartPanLocked).toBe('1');
    expect(host.dataset.editingHandle).toBe('1');
    expect(applyOptions).toHaveBeenCalledWith(chartInteractionForTool(null, true));
    applyChartHostInteraction(host, { applyOptions }, null, false);
    expect(host.dataset.chartPanLocked).toBe('');
    expect(host.dataset.editingHandle).toBe('');
  });
});
