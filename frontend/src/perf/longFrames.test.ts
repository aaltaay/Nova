import { describe, expect, it } from 'vitest';
import {
  basename,
  createLongFrameTally,
  longFrameEntryType,
  scriptSource,
  type LongFrameEntry,
} from './longFrames';

const loaf = (duration: number, blockingDuration: number, scripts: LongFrameEntry['scripts'] = []): LongFrameEntry => ({
  entryType: 'long-animation-frame',
  duration,
  blockingDuration,
  scripts,
});

describe('long frames', () => {
  it('prefers long-animation-frame, falls back to longtask, else nothing', () => {
    expect(longFrameEntryType(['longtask', 'long-animation-frame'])).toBe('long-animation-frame');
    expect(longFrameEntryType(['longtask', 'paint'])).toBe('longtask');
    expect(longFrameEntryType(['paint'])).toBeNull();
    expect(longFrameEntryType(undefined)).toBeNull();
  });

  it('names a script by function and file, without path, query or hash', () => {
    expect(basename('http://127.0.0.1:5173/src/ibkr/DepthLadder.tsx?t=123#x')).toBe('DepthLadder.tsx');
    expect(basename('')).toBe('');
    expect(scriptSource({ duration: 1, sourceFunctionName: 'onmessage', sourceURL: 'file:///C:/app/dist/assets/App-abc.js' }))
      .toBe('onmessage @ App-abc.js');
    expect(scriptSource({ duration: 1 })).toBe('(anonymous) @ (unknown)');
  });

  it('sums LoAF blocking time and ranks the top three scripts by total time', () => {
    const tally = createLongFrameTally();
    const a = { sourceFunctionName: 'applyBook', sourceURL: 'http://x/src/DepthLadder.tsx', invoker: 'WebSocket.onmessage' };
    const b = { sourceFunctionName: 'render', sourceURL: 'http://x/src/TickerChart.tsx', invoker: 'FrameRequestCallback' };
    const c = { sourceFunctionName: 'sort', sourceURL: 'http://x/src/scanner.ts', invoker: 'TimerHandler:setTimeout' };
    const d = { sourceFunctionName: '', sourceURL: 'http://x/src/tiny.ts', invoker: 'DIV.onclick' };
    tally.add(loaf(120.04, 70, [{ ...a, duration: 60 }, { ...b, duration: 50 }]));
    tally.add(loaf(90, 40, [{ ...a, duration: 45 }, { ...c, duration: 30 }, { ...d, duration: 5 }]));
    tally.add(loaf(55, 5, [{ ...c, duration: 40 }]));

    expect(tally.take()).toEqual({
      count: 3,
      blocking_ms: 115,
      max_ms: 120,
      top: [
        { source: 'applyBook @ DepthLadder.tsx', invoker: 'WebSocket.onmessage', ms: 105 },
        { source: 'sort @ scanner.ts', invoker: 'TimerHandler:setTimeout', ms: 70 },
        { source: 'render @ TickerChart.tsx', invoker: 'FrameRequestCallback', ms: 50 },
      ],
    });
  });

  it('counts a longtask as blocking past 50 ms and names no script', () => {
    const tally = createLongFrameTally();
    tally.add({ entryType: 'longtask', duration: 80 });
    tally.add({ entryType: 'longtask', duration: 51.5 });
    expect(tally.take()).toEqual({ count: 2, blocking_ms: 31.5, max_ms: 80, top: [] });
  });

  it('resets on take and clips long names to 200 characters', () => {
    const tally = createLongFrameTally();
    tally.add(loaf(60, 10, [{ duration: 60, sourceFunctionName: 'f'.repeat(300), invoker: 'i'.repeat(300) }]));
    const first = tally.take();
    expect(first.top[0].source).toHaveLength(200);
    expect(first.top[0].invoker).toHaveLength(200);
    expect(tally.take()).toEqual({ count: 0, blocking_ms: 0, max_ms: 0, top: [] });
  });
});
