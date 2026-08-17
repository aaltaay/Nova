import { describe, expect, it } from 'vitest';
import { boundsForTraderWindow } from './traderWindowBounds';

describe('boundsForTraderWindow', () => {
  const a = { x: 0, y: 0, width: 1920, height: 1080 };
  const b = { x: 1920, y: 0, width: 1920, height: 1080 };
  const c = { x: 3840, y: 0, width: 1600, height: 900 };

  it('puts window 0/1/2 on display 0/1/2', () => {
    expect(boundsForTraderWindow([a, b, c], 0, 1440, 900).x).toBe(24);
    expect(boundsForTraderWindow([a, b, c], 1, 1440, 900).x).toBe(1944);
    expect(boundsForTraderWindow([a, b, c], 2, 1440, 900).x).toBe(3864);
  });

  it('cascades extras on the last display when monitors < windows', () => {
    const third = boundsForTraderWindow([a, b], 2, 1440, 900);
    expect(third.x).toBe(1920 + 24 + 36);
    expect(third.y).toBe(24 + 36);
  });
});
