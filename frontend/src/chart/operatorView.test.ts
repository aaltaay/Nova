/**
 * @vitest-environment jsdom
 *
 * Operator report 2026-10-06: zoomed in on the 1-minute pane, the chart "resized itself randomly" -- the plan's
 * lead setup changed and the pane was framed on it. A view the operator zoomed or panned is theirs.
 */
import type { IChartApi, LogicalRangeChangeEventHandler } from 'lightweight-charts';
import { afterEach, describe, expect, it } from 'vitest';
import { OPERATOR_VIEW_SETTLE_MS, operatorOwnsView, releaseView, watchOperatorView } from './operatorView';

function fakeChart() {
  const element = document.createElement('div');
  document.body.appendChild(element);
  const handlers = new Set<LogicalRangeChangeEventHandler>();
  const chart = {
    chartElement: () => element,
    timeScale: () => ({
      subscribeVisibleLogicalRangeChange: (h: LogicalRangeChangeEventHandler) => handlers.add(h),
      unsubscribeVisibleLogicalRangeChange: (h: LogicalRangeChangeEventHandler) => handlers.delete(h),
    }),
  } as unknown as IChartApi;
  let t = 1_000;
  const clock = {
    now: () => t,
    advance: (ms: number) => {
      t += ms;
    },
  };
  const rangeMoves = () => handlers.forEach(h => h({ from: 0, to: 10 } as never));
  return { chart, element, handlers, clock, rangeMoves };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('operatorView (a view the operator moved is theirs)', () => {
  it("counts Nova's own moves as Nova's: a first paint, live follow, a frame", () => {
    const { chart, clock, rangeMoves } = fakeChart();
    watchOperatorView(chart, clock.now);
    rangeMoves();
    expect(operatorOwnsView(chart)).toBe(false);
  });

  it('takes the view on a wheel zoom, even when the range is reported a frame later', () => {
    const { chart, element, clock, rangeMoves } = fakeChart();
    watchOperatorView(chart, clock.now);
    element.dispatchEvent(new WheelEvent('wheel', { deltaY: -120 }));
    clock.advance(16);
    rangeMoves();
    expect(operatorOwnsView(chart)).toBe(true);
  });

  it('takes the view on a drag, and not on a move long after the release', () => {
    const { chart, element, clock, rangeMoves } = fakeChart();
    watchOperatorView(chart, clock.now);
    element.dispatchEvent(new Event('pointerdown'));
    window.dispatchEvent(new Event('pointerup'));
    clock.advance(OPERATOR_VIEW_SETTLE_MS + 1);
    rangeMoves();
    expect(operatorOwnsView(chart)).toBe(false);
    element.dispatchEvent(new Event('pointerdown'));
    clock.advance(2_000); // a slow drag
    rangeMoves();
    expect(operatorOwnsView(chart)).toBe(true);
  });

  it('ignores a press outside the chart (the badge, a splitter) and a wheel long past', () => {
    const { chart, element, clock, rangeMoves } = fakeChart();
    watchOperatorView(chart, clock.now);
    document.body.dispatchEvent(new Event('pointerdown'));
    rangeMoves();
    element.dispatchEvent(new WheelEvent('wheel'));
    clock.advance(OPERATOR_VIEW_SETTLE_MS + 1);
    rangeMoves();
    expect(operatorOwnsView(chart)).toBe(false);
  });

  it('hands the view back on Reset chart or a first paint', () => {
    const { chart, element, clock, rangeMoves } = fakeChart();
    watchOperatorView(chart, clock.now);
    element.dispatchEvent(new WheelEvent('wheel'));
    rangeMoves();
    releaseView(chart);
    expect(operatorOwnsView(chart)).toBe(false);
  });

  it('stops watching when the chart goes', () => {
    const { chart, element, handlers, clock, rangeMoves } = fakeChart();
    const stop = watchOperatorView(chart, clock.now);
    stop();
    expect(handlers.size).toBe(0);
    element.dispatchEvent(new WheelEvent('wheel'));
    rangeMoves();
    expect(operatorOwnsView(chart)).toBe(false);
    expect(operatorOwnsView(null)).toBe(false);
  });
});
