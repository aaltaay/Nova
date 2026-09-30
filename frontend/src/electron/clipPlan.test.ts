/**
 * Share clips' plan (ADR 039): where clips go, what they are called, and how
 * a Trader tab's rectangle maps into a screen segment's frame -- on the
 * desk's own layout (a 4K monitor at 150% left of the 1440p primary).
 */
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  CLIP_DATA_DIR,
  CLIP_HQ_MAX_BPS,
  CLIP_HQ_MIN_BPS,
  CLIP_OUT_MAX_WIDTH,
  cleanSymbol,
  cssToDip,
  dipToScreenFrame,
  displayFor,
  etDates,
  exportRelPath,
  hqPlan,
  hqRelPath,
  outputSize,
  pictureDip,
  readRect,
  resolveClipDir,
  retryDelayMs,
  unionRect,
} from '../../electron/clipPlan.mjs';

// The desk's monitors as ADR 035's manifest names them (2026-09-29).
const LEFT_4K = { id: '1037091360', index: 1, bounds: { x: -2560, y: -509, width: 2560, height: 1441 } };
const PRIMARY = { id: '1449598500', index: 3, bounds: { x: 0, y: 0, width: 2560, height: 1440 } };
const geometryOn = (content: { x: number; y: number; width: number; height: number }, zoom = 1) => ({
  window_id: 'main',
  display_id: PRIMARY.id,
  content,
  inner: { w: content.width / zoom, h: content.height / zoom },
  pane: { x: 200, y: 90, w: 1200, h: 700 },
  panels: { plan: { x: 1000, y: 120, w: 300, h: 150 }, charts: { x: 200, y: 120, w: 700, h: 600 } },
});

describe('resolveClipDir', () => {
  it('prefers NOVA_CLIPS_DIR, then F:\\Nova\\clips, then the app folder and says so', () => {
    expect(resolveClipDir({ env: { NOVA_CLIPS_DIR: 'E:\\clips' }, dataDriveMounted: true, userData: 'U', join: path.join }).source).toBe('env');
    expect(resolveClipDir({ env: {}, dataDriveMounted: true, userData: 'U', join: path.join })).toEqual({ dir: CLIP_DATA_DIR, source: 'data_drive', note: null });
    const fb = resolveClipDir({ env: {}, dataDriveMounted: false, userData: 'U', join: path.join });
    expect(fb.source).toBe('fallback');
    expect(fb.note).toMatch(/not mounted/);
  });
});

describe('file names', () => {
  it('names an export by symbol and Eastern start time, and never reuses one', () => {
    const ms = Date.UTC(2026, 8, 24, 12, 6, 16); // 08:06:16 ET
    expect(exportRelPath(ms, 'PFSA')).toEqual({ date: '2026-09-24', name: 'PFSA-080616.mp4' });
    expect(exportRelPath(ms, 'BRK/B', 2).name).toBe('BRK-B-080616-2.mp4');
    expect(hqRelPath(ms, 'PFSA', 'video/x-matroska;codecs=avc1')).toEqual({ date: '2026-09-24', name: '080616-PFSA-hq.mkv' });
    expect(hqRelPath(ms, 'PFSA', 'video/webm;codecs=vp9').name.endsWith('.webm')).toBe(true);
  });

  it('lists every Eastern date a clip spans, midnight included', () => {
    const start = Date.UTC(2026, 8, 25, 3, 50); // 23:50 ET on the 24th
    expect(etDates(start, start + 20 * 60_000)).toEqual(['2026-09-24', '2026-09-25']);
  });

  it('takes only ticker-shaped symbols', () => {
    expect(cleanSymbol(' pfsa ')).toBe('PFSA');
    expect(cleanSymbol('BRK/B')).toBe('BRK/B');
    expect(cleanSymbol('../x')).toBeNull();
    expect(cleanSymbol('')).toBeNull();
  });
});

describe('sizes and rates', () => {
  it('caps a high-quality capture and keeps its bitrate inside the bounds', () => {
    const big = hqPlan(3840, 2100);
    expect(big.maxWidth).toBeLessThanOrEqual(2560);
    expect(big.maxWidth % 2 + big.maxHeight % 2).toBe(0);
    expect(big.bps).toBeLessThanOrEqual(CLIP_HQ_MAX_BPS);
    expect(hqPlan(200, 100).bps).toBe(CLIP_HQ_MIN_BPS);
  });

  it('exports the tab as it is, capped and even', () => {
    expect(outputSize(1201, 701)).toEqual({ width: 1200, height: 700 });
    expect(outputSize(2560, 1400).width).toBe(CLIP_OUT_MAX_WIDTH);
  });

  it('backs off a lost capture like the screen recorder and never gives up', () => {
    expect(retryDelayMs(1)).toBe(2_000);
    expect(retryDelayMs(99)).toBe(60_000);
  });
});

describe('rectangles', () => {
  it('reads a rectangle once, and unions panels', () => {
    expect(readRect({ x: 1, y: 2, w: 3, h: 4 })).toEqual({ x: 1, y: 2, w: 3, h: 4 });
    expect(readRect({ x: 1, y: 2, w: 0, h: 4 })).toBeNull();
    expect(readRect({ x: 'a', y: 2, w: 3, h: 4 })).toBeNull();
    expect(unionRect([{ x: 0, y: 0, w: 10, h: 10 }, { x: 20, y: 5, w: 5, h: 20 }])).toEqual({ x: 0, y: 0, w: 25, h: 25 });
  });

  it('turns page pixels into DIP through the page zoom', () => {
    const g = geometryOn({ x: 0, y: 23, width: 2560, height: 1392 }, 1.25);
    expect(cssToDip({ x: 100, y: 100, w: 400, h: 200 }, g)).toEqual({ x: 125, y: 125, w: 500, h: 250 });
  });

  it('maps the tab into the primary monitor recording one to one', () => {
    const g = geometryOn({ x: 0, y: 23, width: 2560, height: 1392 });
    const dip = pictureDip(g, 'trader_tab');
    expect(dipToScreenFrame(dip, g, PRIMARY, 2560, 1440)).toEqual({ x: 200, y: 113, w: 1200, h: 700 });
  });

  it('maps a tab on the 150% monitor into its layout-size recording', () => {
    const g = { ...geometryOn({ x: -2560, y: -486, width: 2560, height: 1418 }), display_id: LEFT_4K.id };
    const px = dipToScreenFrame(pictureDip(g, 'trader_tab'), g, LEFT_4K, 2560, 1440);
    // 1441 DIP tall recorded at 1440: a hair under one to one, rounded outward so nothing is cut.
    expect(px).toEqual({ x: 200, y: 112, w: 1200, h: 701 });
    expect(displayFor(g, [LEFT_4K, PRIMARY])?.id).toBe(LEFT_4K.id);
  });

  it('picks panels, the whole page or nothing', () => {
    const g = geometryOn({ x: 0, y: 23, width: 2560, height: 1392 });
    expect(pictureDip(g, 'panels', ['charts', 'plan'])).toEqual({ x: 200, y: 120, w: 1100, h: 600 });
    expect(pictureDip(g, 'window')).toEqual({ x: 0, y: 0, w: 2560, h: 1392 });
    expect(pictureDip(g, 'panels', ['tape'])).toBeNull();
    expect(pictureDip(null, 'trader_tab')).toBeNull();
  });

  it('clamps a crop that runs off the frame', () => {
    const g = { ...geometryOn({ x: 2000, y: 23, width: 2560, height: 1392 }), pane: { x: 0, y: 0, w: 1000, h: 500 } };
    expect(dipToScreenFrame(pictureDip(g, 'trader_tab'), g, PRIMARY, 2560, 1440)).toEqual({ x: 2000, y: 23, w: 560, h: 500 });
  });
});
