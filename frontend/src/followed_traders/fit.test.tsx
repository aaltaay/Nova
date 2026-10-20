/**
 * @vitest-environment jsdom
 *
 * `useFitLevel` measures its way to the smallest fold level that fits. A day with more than ~50 closed trades across
 * the hosts once walked there one level per render and hit React's nested-update limit ("Maximum update depth
 * exceeded", React #185), blanking Bots > LiveTrader Bots (2026-10-20, 51 closed trades).
 */
import { cleanup, render, screen } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useFitLevel } from './fit';

const BOX = 100;
/** The drawn content's height at a fold level: each level saves 10 px, from 1,000 px at level 0. */
const contentAt = (level: number): number => Math.max(0, 1000 - 10 * level);

function Probe({ shape, max }: { shape: string; max: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const { level, overflowing } = useFitLevel(ref, shape, max);
  return <div ref={ref} data-testid="box" data-level={level} data-over={String(overflowing)} />;
}

describe('useFitLevel', () => {
  const realScroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollHeight');
  const realClient = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientHeight');

  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => BOX });
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get(this: HTMLElement) { return contentAt(Number(this.dataset.level ?? 0)); },
    });
  });
  afterEach(() => {
    cleanup();
    if (realScroll) Object.defineProperty(HTMLElement.prototype, 'scrollHeight', realScroll);
    if (realClient) Object.defineProperty(HTMLElement.prototype, 'clientHeight', realClient);
  });

  it('finds a deep fold level without exceeding React update depth', () => {
    // 1000 - 10 * level <= 101 first at level 90: far past the 50 nested updates React allows.
    render(<Probe shape="a" max={200} />);
    const box = screen.getByTestId('box');
    expect(box.dataset.level).toBe('90');
    expect(box.dataset.over).toBe('false');
  });

  it('stays at level 0 when everything fits', () => {
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, get: () => 50 });
    render(<Probe shape="a" max={10} />);
    expect(screen.getByTestId('box').dataset.level).toBe('0');
  });

  it('stops at the last level and says it overflows when even that does not fit', () => {
    render(<Probe shape="a" max={60} />);
    const box = screen.getByTestId('box');
    expect(box.dataset.level).toBe('60');
    expect(box.dataset.over).toBe('true');
  });
});
