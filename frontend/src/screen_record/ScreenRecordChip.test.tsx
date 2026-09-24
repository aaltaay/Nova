/** @vitest-environment jsdom */
/**
 * The header's screen recording chip (ADR 035): quiet while every monitor
 * records, loud the moment one does not, and honest in a browser, which
 * cannot record the screen at all.
 */
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ScreenRecordChip } from './ScreenRecordChip';
import { screenChip } from './screenRecordChipModel';
import { readScreenRecordView } from './screenRecordView';

const GB = 1024 ** 3;

function wire(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    state: 'recording',
    recording: true,
    since: 1790257440, // 2026-09-24 09:44:00 ET
    error: null,
    dir: 'F:\\Nova\\screen',
    dir_source: 'data_drive',
    dir_note: null,
    dir_error: null,
    mime: 'video/x-matroska;codecs=avc1',
    fps: 15,
    segment_min: 15,
    displays: [
      { index: 1, count: 2, id: '11', label: 'left', primary: false, scale_factor: 1.5, width: 2560, height: 1440, recording: true, since: 1790257440, file: '094400-screen1.mkv', bytes: 1000, last_data_ts: 1790257500, error: null, retry_at: null },
      { index: 2, count: 2, id: '22', label: 'main', primary: true, scale_factor: 1, width: 1920, height: 1080, recording: true, since: 1790257440, file: '094400-screen2.mkv', bytes: 1000, last_data_ts: 1790257500, error: null, retry_at: null },
    ],
    unmatched: [],
    disk: { free_bytes: 800 * GB, state: 'ok', error: null, checked_ts: 1790257440 },
    problems: [],
    restarts: 0,
    generated_at: 1790257500,
    ...over,
  };
}

function bridge(initial: unknown) {
  let listener: ((view: unknown) => void) | null = null;
  return {
    subscribe: (onView: (view: unknown) => void) => {
      listener = onView;
      onView(initial);
      return () => {
        listener = null;
      };
    },
    push: (view: unknown) => listener?.(view),
  };
}

describe('readScreenRecordView', () => {
  it('reads the wire and refuses what it does not know', () => {
    const view = readScreenRecordView(wire());
    expect(view?.state).toBe('recording');
    expect(view?.displays.map((d) => d.file)).toEqual(['094400-screen1.mkv', '094400-screen2.mkv']);
    expect(view?.disk).toEqual({ freeBytes: 800 * GB, state: 'ok' });
    expect(readScreenRecordView(wire({ schema_version: 2 }))).toBeNull();
    expect(readScreenRecordView(wire({ state: 'maybe' }))).toBeNull();
    expect(readScreenRecordView('nope')).toBeNull();
  });
});

describe('screenChip', () => {
  it('is only an icon while every monitor records, with the details on hover', () => {
    const chip = screenChip(readScreenRecordView(wire()), true);
    expect(chip.tone).toBe('quiet');
    expect(chip.label).toBeNull();
    expect(chip.tip).toContain('Recording all 2 monitors since 09:44:00 ET.');
    expect(chip.tip).toContain('Monitor 2 (main): 1920x1080 -> 094400-screen2.mkv');
    expect(chip.tip).toContain('Folder: F:\\Nova\\screen');
    expect(chip.tip).toContain('H.264, 15 fps, a new file every 15 minutes.');
    expect(chip.tip).toContain('F: has 800 GB free');
  });

  it('shouts when the screen is not recorded, and says why', () => {
    const chip = screenChip(
      readScreenRecordView(wire({
        state: 'failed',
        recording: false,
        error: 'the recorder process ended (crashed)',
        displays: [{ index: 1, count: 1, primary: true, width: 1920, height: 1080, recording: false, error: 'the recorder process ended (crashed)', retry_at: 1790257505 }],
        problems: [{ at: 1790257490, display_index: 1, reason: 'recorder_gone', detail: 'the recorder process ended (crashed)', resumed_at: null }],
      })),
      true,
    );
    expect(chip.tone).toBe('loud');
    expect(chip.label).toBe('Screen not recording');
    expect(chip.tip).toMatch(/^YOUR SCREEN IS NOT BEING RECORDED: the recorder process ended \(crashed\)/);
    expect(chip.tip).toContain('Monitor 1 (main): NOT RECORDING -- the recorder process ended (crashed), trying again at 09:45:05 ET');
    expect(chip.tip).toContain('09:44:50 ET: monitor 1 stopped (the recorder process ended (crashed)), not back yet');
  });

  it('counts the monitors when only some are recorded', () => {
    const view = wire({ state: 'partial', recording: false });
    (view.displays[1] as Record<string, unknown>).recording = false;
    expect(screenChip(readScreenRecordView(view), true)).toMatchObject({ tone: 'loud', label: 'Screen: 1 of 2 recorded' });
  });

  it('warns about a filling drive and a recording on the system drive', () => {
    expect(screenChip(readScreenRecordView(wire({ disk: { free_bytes: 40 * GB, state: 'warn' } })), true))
      .toMatchObject({ tone: 'warn', label: 'Screen: 40 GB free' });
    expect(screenChip(readScreenRecordView(wire({ disk: { free_bytes: 5 * GB, state: 'fail' } })), true))
      .toMatchObject({ tone: 'loud', label: 'Screen: 5.0 GB left' });
    expect(screenChip(readScreenRecordView(wire({ dir_source: 'fallback', dir_note: 'F: is not mounted, so the screen records to the system drive' })), true))
      .toMatchObject({ tone: 'warn', label: 'Screen on system drive' });
  });

  it('tells a browser desk that the screen is not recorded there', () => {
    expect(screenChip(null, false)).toMatchObject({ tone: 'warn', label: 'Screen not recorded' });
  });
});

describe('ScreenRecordChip', () => {
  afterEach(cleanup);

  it('follows the desktop app as the recording changes', () => {
    const b = bridge(wire());
    render(<ScreenRecordChip bridge={b} />);
    const chip = screen.getByTestId('screen-rec-chip');
    expect(chip.dataset.state).toBe('recording');
    expect(chip.textContent).toBe('');
    expect(chip.getAttribute('data-tip')).toContain('Recording all 2 monitors');
    act(() => b.push(wire({ state: 'failed', recording: false, error: 'Windows gave Nova no screen to capture', displays: [] })));
    expect(chip.dataset.state).toBe('failed');
    expect(chip.textContent).toBe('Screen not recording');
    expect(chip.className).toContain('screen-rec-chip--loud');
  });

  it('says "not recorded" in a browser window', () => {
    render(<ScreenRecordChip bridge={null} />);
    const chip = screen.getByTestId('screen-rec-chip');
    expect(chip.dataset.state).toBe('browser');
    expect(chip.textContent).toBe('Screen not recorded');
  });
});
