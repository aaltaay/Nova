/**
 * @vitest-environment jsdom
 */
import { act, cleanup, renderHook } from '@testing-library/react';
import type { IChartApi, MouseEventParams, Time } from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { areaHoverId } from '../chart';
import { setCandleCardOpen } from '../chart/hoverTarget';
import { useShapeHover } from './ShapeTip';

type Move = (p: MouseEventParams<Time>) => void;

function setup() {
  let move: Move = () => {};
  const chart = {
    subscribeCrosshairMove: vi.fn((fn: Move) => { move = fn; }),
    unsubscribeCrosshairMove: vi.fn(),
  } as unknown as IChartApi;
  const boxRef = { current: document.createElement('div') };
  const hook = renderHook(() => useShapeHover(chart, true, boxRef));
  const at = (hoveredObjectId: string) =>
    act(() => move({ point: { x: 40, y: 80 } as never, hoveredObjectId, seriesData: new Map() } as MouseEventParams<Time>));
  const candleCard = (open: boolean) => act(() => setCandleCardOpen(chart, open));
  return { hook, at, candleCard };
}

describe('useShapeHover', () => {
  afterEach(cleanup);

  it("names a box's story by its own id, over its area or its label", () => {
    const { hook, at } = setup();
    at(areaHoverId('past:a'));
    expect(hook.result.current).toMatchObject({ id: 'past:a', area: true });
    at('past:a');
    expect(hook.result.current).toMatchObject({ id: 'past:a', area: false });
  });

  it("steps aside over a box's area while the candle card is open, and comes back when it closes", () => {
    const { hook, at, candleCard } = setup();
    at(areaHoverId('past:a'));
    candleCard(true);
    expect(hook.result.current).toBeNull();
    candleCard(false);
    expect(hook.result.current).toMatchObject({ id: 'past:a' });
  });

  it('keeps a story told at a point', () => {
    const { hook, at, candleCard } = setup();
    candleCard(true);
    at('level:7.00');
    expect(hook.result.current).toMatchObject({ id: 'level:7.00', area: false });
  });
});
