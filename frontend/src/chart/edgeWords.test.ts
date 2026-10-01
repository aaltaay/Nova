import { describe, expect, it, vi } from 'vitest';
import type { IChartApi, ISeriesApi, SeriesType } from 'lightweight-charts';
import {
  EDGE_PRIORITY,
  claimEdge,
  edgeClaimed,
  edgeContents,
  emaPriority,
  publishEdgeReserves,
  publishEdgeWords,
  subscribeEdge,
  type EdgeWord,
} from './edgeWords';

const chart = () => ({}) as IChartApi;
const series = {} as ISeriesApi<SeriesType>;
const word = (id: string, text = id): EdgeWord => ({ id, text, color: '#fff', priority: 50, series, valueWhenOff: true });

describe('the edge registry (who lays out a pane\'s right edge)', () => {
  it('is unclaimed until a claim, and the claim is given back once', () => {
    const c = chart();
    expect(edgeClaimed(c)).toBe(false);
    const release = claimEdge(c);
    const second = claimEdge(c);
    expect(edgeClaimed(c)).toBe(true);
    release();
    release(); // twice is once
    expect(edgeClaimed(c)).toBe(true);
    second();
    expect(edgeClaimed(c)).toBe(false);
    expect(edgeClaimed(null)).toBe(false);
  });

  it('keeps each source\'s words, and an empty list takes them back', () => {
    const c = chart();
    publishEdgeWords(c, 'overlays', [word('ema9'), word('vwap')]);
    publishEdgeWords(c, 'other', [word('x')]);
    expect(edgeContents(c).words.map(w => w.id)).toEqual(['ema9', 'vwap', 'x']);
    publishEdgeWords(c, 'overlays', []);
    expect(edgeContents(c).words.map(w => w.id)).toEqual(['x']);
  });

  it('hands out one snapshot until something changes, and says when it does', () => {
    const c = chart();
    const fn = vi.fn();
    const stop = subscribeEdge(c, fn);
    publishEdgeWords(c, 'overlays', [word('ema9')]);
    const first = edgeContents(c);
    expect(edgeContents(c)).toBe(first);
    publishEdgeWords(c, 'overlays', [word('ema9')]); // the same words: no news
    expect(fn).toHaveBeenCalledTimes(1);
    publishEdgeWords(c, 'overlays', [word('ema9', '9 EMA')]);
    expect(fn).toHaveBeenCalledTimes(2);
    expect(edgeContents(c)).not.toBe(first);
    publishEdgeReserves(c, 'position', [{ id: 'position', price: 4.8, height: 20 }]);
    expect(edgeContents(c).reserves).toEqual([{ id: 'position', price: 4.8, height: 20 }]);
    const release = claimEdge(c);
    expect(fn).toHaveBeenCalledTimes(4);
    stop();
    release();
    expect(fn).toHaveBeenCalledTimes(4);
  });

  it('ranks the plan\'s lines over VWAP, the levels over the EMAs, and the 9 EMA first of them', () => {
    expect(EDGE_PRIORITY.planLine).toBeGreaterThan(EDGE_PRIORITY.vwap);
    expect(EDGE_PRIORITY.level).toBeGreaterThan(emaPriority(9));
    expect(emaPriority(9)).toBeGreaterThan(emaPriority(20));
    expect(emaPriority(20)).toBeGreaterThan(emaPriority(200));
    expect(emaPriority(200)).toBeGreaterThan(EDGE_PRIORITY.offView);
  });
});
