/** @vitest-environment jsdom */
/**
 * Share clips on the desk (ADR 039), with a fake desktop bridge: the tab
 * report measures the active pane, the Record menu starts and stops a clip
 * (a stop raises the toast that offers the export), a locked control says
 * why, the chips follow the view, and Records › Video clips gives each row
 * the actions of its state.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildClipTabReport } from './clipTabReport';
import { ClipChips } from './ClipChips';
import { ClipsList } from './ClipsList';
import { ClipToasts } from './ClipToasts';
import { _resetClipsStoreForTests, getClipToasts, pushClipToast } from './clipsStore';

vi.mock('../workspace', () => ({ useWorkspace: () => ({ showScannerView: vi.fn() }), setNavPage: vi.fn() }));
vi.mock('../capture', () => ({
  CAPTURE_STOP_HOLD_HINT: 'Press and hold.',
  captureStopHoldLabel: (s: string) => `Hold to stop recording ${s}`,
  getRecordingSymbols: () => [],
  getSessionRecordError: () => null,
  getSessionRecordVersion: () => 0,
  HoldToStopButton: () => null,
  isTabRecording: () => false,
  startTabRecord: vi.fn(async () => null),
  stopTabRecord: vi.fn(async () => null),
  subscribeSessionRecord: () => () => undefined,
}));

const T0 = Math.round(Date.now() / 1000) - 72;
function viewOf(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    generated_at: T0 + 72,
    dir: 'F:\\Nova\\clips',
    dir_source: 'data_drive',
    hq_max: 2,
    hq_in_use: 0,
    hq_max_sec: 1800,
    hq_warn_sec: 60,
    last_n_sec: 300,
    open: [],
    clips: [],
    tabs: [{ window_id: 'main', symbol: 'PFSA', visible: true, display_id: 'd3', screen_recording: true }],
    disk: { free_bytes: 790 * 1024 ** 3, state: 'ok' },
    ...over,
  };
}

let push: (v: unknown) => void = () => undefined;
let act_: ReturnType<typeof vi.fn>;
function installBridge(initial: unknown) {
  act_ = vi.fn(async () => ({ ok: true }));
  window.novaDesktop = {
    isDesktop: true,
    apiBase: '',
    getVersion: async () => 'test',
    clips: {
      subscribe: (onView) => {
        push = onView;
        onView(initial);
        return () => undefined;
      },
      act: act_,
      report: vi.fn(),
    },
  };
}

beforeEach(() => {
  _resetClipsStoreForTests();
});
afterEach(() => {
  cleanup();
  delete window.novaDesktop;
  vi.useRealTimers();
});

describe('buildClipTabReport', () => {
  it('measures the active pane and its panels, and says why a tab is not on screen', () => {
    document.body.innerHTML = '<div id="root"><div data-testid="sv-tab-pane-PFSA"><div data-testid="stock-read-plan"></div></div></div>';
    const pane = document.querySelector('[data-testid="sv-tab-pane-PFSA"]')!;
    const plan = document.querySelector('[data-testid="stock-read-plan"]')!;
    pane.getBoundingClientRect = () => ({ left: 200, top: 90, width: 1200, height: 700 }) as DOMRect;
    plan.getBoundingClientRect = () => ({ left: 1000, top: 120, width: 300, height: 150 }) as DOMRect;
    const root = document.getElementById('root');
    const r = buildClipTabReport({ windowId: 'main', symbol: 'PFSA', onScreen: true, root });
    expect(r).toMatchObject({ schema_version: 1, window_id: 'main', visible: true, reason: null, pane: { x: 200, y: 90, w: 1200, h: 700 }, panels: { plan: { x: 1000, y: 120, w: 300, h: 150 } } });
    expect(buildClipTabReport({ windowId: 'main', symbol: 'PFSA', onScreen: false, root })).toMatchObject({ visible: false, reason: 'page', pane: null });
    expect(buildClipTabReport({ windowId: 'main', symbol: null, onScreen: true, root })).toMatchObject({ visible: false, reason: 'draft' });
  });

  it('measures a panel of several parts as the box around them (the rail quote: price head and stats)', () => {
    document.body.innerHTML = '<div id="root"><div data-testid="sv-tab-pane-PFSA">'
      + '<div data-testid="stock-view-quote-head"></div><div data-testid="stock-view-quote-stats"></div></div></div>';
    const at = (id: string, r: { left: number; top: number; width: number; height: number }) => {
      document.querySelector(`[data-testid="${id}"]`)!.getBoundingClientRect = () => r as DOMRect;
    };
    at('sv-tab-pane-PFSA', { left: 200, top: 90, width: 1200, height: 700 });
    at('stock-view-quote-head', { left: 1320, top: 140, width: 340, height: 30 });
    at('stock-view-quote-stats', { left: 1320, top: 172, width: 350, height: 44 });
    const r = buildClipTabReport({ windowId: 'main', symbol: 'PFSA', onScreen: true, root: document.getElementById('root') });
    expect((r.panels as Record<string, unknown>).quote).toEqual({ x: 1320, y: 140, w: 350, h: 76 });
  });
});

describe('the Record menu', () => {
  it('starts a clip, then stops it and offers the export', async () => {
    installBridge(viewOf());
    const { RecordButton } = await import('./RecordButton');
    render(<RecordButton symbol="PFSA" />);
    fireEvent.click(screen.getByTestId('clip-record-button'));
    fireEvent.click(await screen.findByTestId('clip-menu-start'));
    await waitFor(() => expect(act_).toHaveBeenCalledWith({ action: 'start', symbol: 'PFSA', hq: false, origin: 'button' }));
    // A start that worked closes the menu: it would sit over Level 2, and the button counts instead.
    await waitFor(() => expect(screen.queryByTestId('clip-menu-start')).toBeNull());
    act(() => push(viewOf({ open: [{ clip_id: 'c1', symbol: 'PFSA', started_ts: T0, state: 'ok', screen_recording: true, hq: null }] })));
    expect(screen.getByTestId('clip-record-button').textContent).toMatch(/1:1\d/);
    fireEvent.click(screen.getByTestId('clip-record-button'));
    act_.mockResolvedValueOnce({ ok: true, clip: { clip_id: 'c1', length_sec: 72 } });
    fireEvent.click(await screen.findByTestId('clip-menu-stop'));
    await waitFor(() => expect(getClipToasts()[0]).toMatchObject({ kind: 'saved', clipId: 'c1' }));
  });

  it('locks High quality at the cap and says why, and shows a refused start', async () => {
    installBridge(viewOf({ hq_in_use: 2 }));
    const { RecordButton } = await import('./RecordButton');
    render(<RecordButton symbol="PFSA" />);
    fireEvent.click(screen.getByTestId('clip-record-button'));
    const box = (await screen.findByTestId('clip-menu-hq')).querySelector('input')!;
    expect(box.disabled).toBe(true);
    expect(box.getAttribute('data-why')).toMatch(/Both high-quality captures/);
    act_.mockResolvedValueOnce({ ok: false, error: "Open PFSA's Trader tab first: a clip records the tab." });
    fireEvent.click(screen.getByTestId('clip-menu-start'));
    expect((await screen.findByTestId('clip-menu-error')).textContent).toMatch(/Trader tab first/);
  });

  it('says a browser tab cannot record video', async () => {
    const { RecordButton } = await import('./RecordButton');
    render(<RecordButton symbol="PFSA" />);
    fireEvent.click(screen.getByTestId('clip-record-button'));
    expect((await screen.findByTestId('clip-menu-start')).getAttribute('data-why')).toMatch(/desktop app/);
  });
});

describe('the CLIP chips', () => {
  it('shows each open clip, with High quality and its state', async () => {
    installBridge(viewOf({
      open: [
        { clip_id: 'c1', symbol: 'PFSA', started_ts: T0, state: 'ok', screen_recording: true, hq: { since: T0, ends_at: T0 + 1800, recording: true, lost: false } },
        { clip_id: 'c2', symbol: 'APUS', started_ts: T0, state: 'hidden', reason: 'symbol', showing: 'NVDA', screen_recording: true, hq: null },
      ],
    }));
    render(<ClipChips />);
    const chips = screen.getAllByTestId('clip-chip');
    expect(chips.map((c) => c.getAttribute('data-symbol'))).toEqual(['PFSA', 'APUS']);
    expect((chips[0]).textContent).toMatch('HQ');
    expect(chips[1].className).toMatch(/clip-chip--dim/);
    fireEvent.mouseEnter(chips[1]);
    expect((screen.getByTestId('clip-card')).textContent).toMatch(/shows NVDA/);
  });
});

describe('Records › Video clips', () => {
  it('gives each row the actions of its state', async () => {
    installBridge(viewOf({
      clips: [
        { clip_id: 'a', symbol: 'PFSA', started_ts: T0, ended_ts: T0 + 198, status: 'ready', length_sec: 198, hq_sec: 198, export: { export_id: 'e1', state: 'done', file: '2026-09-24/PFSA-080616.mp4', bytes: 44 * 1024 ** 2, picture: 'trader_tab', blur: [] } },
        { clip_id: 'b', symbol: 'APUS', started_ts: T0, ended_ts: T0 + 172, status: 'exporting', length_sec: 172, export: { export_id: 'e2', state: 'running', progress: 0.45 } },
        { clip_id: 'c', symbol: 'MSS', started_ts: T0, ended_ts: T0 + 210, status: 'failed', length_sec: 210, export: { export_id: 'e3', state: 'failed', error: 'F: was full' } },
      ],
    }));
    render(<ClipsList onOpenTrader={() => undefined} />);
    const rows = screen.getAllByTestId('clip-row');
    expect((rows[0]).textContent).toMatch(/Ready/);
    expect((rows[0]).textContent).toMatch(/Show in folder/);
    expect((rows[0]).textContent).toMatch('44 MB');
    expect((rows[1]).textContent).toMatch(/Exporting 45%/);
    expect((rows[2]).textContent).toMatch(/Export failed: F: was full/);
    fireEvent.click(rows[1].querySelector('button')!);
    await waitFor(() => expect(act_).toHaveBeenCalledWith({ action: 'cancel_export', export_id: 'e2' }));
  });

  it('says a browser desk has no clips', () => {
    render(<ClipsList onOpenTrader={() => undefined} />);
    expect((screen.getByTestId('clips-no-desktop')).textContent).toMatch(/desktop app/);
  });
});

describe('the toasts', () => {
  it('offers the export for a stopped clip and leaves after a while', async () => {
    vi.useFakeTimers();
    installBridge(viewOf({ clips: [{ clip_id: 'c1', symbol: 'PFSA', started_ts: T0, ended_ts: T0 + 198, status: 'not_exported', length_sec: 198 }] }));
    render(<ClipToasts />);
    act(() => pushClipToast({ kind: 'saved', clipId: 'c1', clip: null, text: 'PFSA' }));
    expect((screen.getByTestId('clip-toast')).textContent).toMatch(/Clip saved · PFSA 3:18/);
    expect(screen.getByTestId('clip-toast-export')).toBeTruthy();
    act(() => vi.advanceTimersByTime(13_000));
    expect(screen.queryByTestId('clip-toast')).toBeNull();
  });
});
