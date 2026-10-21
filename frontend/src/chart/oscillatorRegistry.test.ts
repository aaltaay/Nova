import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import {
  oscillatorPane,
  publishOscillatorPane,
  subscribeOscillatorPane,
  type OscillatorPaneHandle,
} from './oscillatorRegistry';

const chart = () => ({}) as IChartApi;
const handle = (kind: 'macd' | 'rsi' = 'macd'): OscillatorPaneHandle => ({
  kind,
  chart: chart(),
  line: {} as ISeriesApi<'Line'>,
});

describe('oscillatorRegistry', () => {
  it('hands a subscriber what is there at once, then every change', () => {
    const parent = chart();
    const h = handle();
    publishOscillatorPane(parent, 'macd', h);
    const cb = vi.fn();
    const stop = subscribeOscillatorPane(parent, 'macd', cb);
    expect(cb).toHaveBeenLastCalledWith(h);
    publishOscillatorPane(parent, 'macd', null);
    expect(cb).toHaveBeenLastCalledWith(null);
    expect(oscillatorPane(parent, 'macd')).toBeNull();
    stop();
    publishOscillatorPane(parent, 'macd', handle());
    expect(cb).toHaveBeenCalledTimes(2);
  });

  it('keeps kinds and parent charts apart', () => {
    const a = chart();
    const b = chart();
    const rsi = vi.fn();
    subscribeOscillatorPane(a, 'rsi', rsi);
    publishOscillatorPane(a, 'macd', handle());
    publishOscillatorPane(b, 'rsi', handle('rsi'));
    expect(rsi).toHaveBeenCalledTimes(1);
    expect(rsi).toHaveBeenCalledWith(null);
    expect(oscillatorPane(a, 'macd')).not.toBeNull();
    expect(oscillatorPane(b, 'macd')).toBeNull();
  });

  it('does not announce the same pane twice, and answers null without a parent', () => {
    const parent = chart();
    const h = handle();
    const cb = vi.fn();
    subscribeOscillatorPane(parent, 'macd', cb);
    publishOscillatorPane(parent, 'macd', h);
    publishOscillatorPane(parent, 'macd', { ...h });
    expect(cb).toHaveBeenCalledTimes(2);
    const none = vi.fn();
    subscribeOscillatorPane(null, 'macd', none)();
    expect(none).toHaveBeenCalledWith(null);
    expect(oscillatorPane(null, 'macd')).toBeNull();
  });
});
