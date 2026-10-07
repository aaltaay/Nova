/**
 * @vitest-environment jsdom
 *
 * The day cover's alarm (ADR 048 decision 5, step 6): a short Nova could not cover is a red bar in every desk
 * window, mounted with the bot's notices, until a cover goes out or the short is gone. This window may hide one
 * for ten minutes; it comes back after.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DAY_COVER_ALARM_HIDE_MS } from '../constantGroups/bots_page';
import { BotNotices } from './BotNotices';
import { DayCoverAlarms, shownAlarms } from './DayCoverAlarms';
import type { CoverAlarm } from './types';

const state: { alarms: CoverAlarm[] } = { alarms: [] };
vi.mock('./useBotSession', () => ({
  useBotSession: () => ({ session: { shorts: { day_cover: { alarms: state.alarms } } }, audit: [] }),
}));

const NOW = Date.UTC(2026, 9, 7, 19, 56);

function alarm(partial: Partial<CoverAlarm> = {}): CoverAlarm {
  return {
    id: 'live:RDYN', venue: 'live', symbol: 'RDYN', qty: 416, kind: 'refused', since: NOW / 1000,
    updated: NOW / 1000, error: 'IBKR refused the cover', reason_code: 'DAY_COVER_CANCEL',
    text: 'Nova could not cover 416 RDYN short on Live: IBKR refused the cover. Cover it yourself now; '
      + 'Nova tries again every 15 s.',
    last_seen: null, ...partial,
  };
}

beforeEach(() => { state.alarms = []; });
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('shownAlarms', () => {
  it('shows every alarm except one hidden here until a moment still ahead', () => {
    const a = alarm();
    const b = alarm({ id: 'paper:XYZ', venue: 'paper', symbol: 'XYZ' });
    expect(shownAlarms([a, b], {}, NOW).map(x => x.id)).toEqual(['live:RDYN', 'paper:XYZ']);
    expect(shownAlarms([a, b], { 'live:RDYN': NOW + 1 }, NOW).map(x => x.id)).toEqual(['paper:XYZ']);
    expect(shownAlarms([a, b], { 'live:RDYN': NOW }, NOW).map(x => x.id)).toEqual(['live:RDYN', 'paper:XYZ']);
  });
});

describe('DayCoverAlarms', () => {
  it('draws nothing while no short waits on its cover', () => {
    render(<DayCoverAlarms />);
    expect(screen.queryByTestId('day-cover-alarms')).toBeNull();
  });

  it('names the venue, the stock and the shares, in words, as an alert', () => {
    state.alarms = [alarm(), alarm({ id: 'paper:XYZ', venue: 'paper', symbol: 'XYZ', qty: 100, kind: 'outside_session',
      text: 'Paper stands outside the regular session.' })];
    render(<DayCoverAlarms />);
    const bars = screen.getAllByTestId('day-cover-alarm');
    expect(bars).toHaveLength(2);
    expect(screen.getByTestId('day-cover-alarms').getAttribute('role')).toBe('alert');
    expect(bars[0].textContent).toContain('DAY COVER · Live · RDYN 416 ▼ SHORT');
    expect(bars[0].textContent).toContain('Cover it yourself now');
    expect(bars[0].getAttribute('data-kind')).toBe('refused');
    expect(bars[1].textContent).toContain('DAY COVER · Paper · XYZ 100 ▼ SHORT');
  });

  it('hides one here for ten minutes, then shows it again', () => {
    vi.useFakeTimers({ now: NOW });
    state.alarms = [alarm()];
    render(<DayCoverAlarms />);
    act(() => { fireEvent.click(screen.getByTestId('day-cover-alarm-hide')); });
    expect(screen.queryByTestId('day-cover-alarms')).toBeNull();
    act(() => { vi.advanceTimersByTime(DAY_COVER_ALARM_HIDE_MS - 30_000); });
    expect(screen.queryByTestId('day-cover-alarms')).toBeNull();
    act(() => { vi.advanceTimersByTime(45_000); });
    expect(screen.getByTestId('day-cover-alarm').textContent).toContain('RDYN');
  });

  it('rides with the bot\'s notices, so every window shows it', () => {
    state.alarms = [alarm()];
    render(<BotNotices />);
    expect(screen.getByTestId('day-cover-alarm').textContent).toContain('RDYN 416');
    expect(screen.queryByTestId('bot-notices')).toBeNull();
  });
});
