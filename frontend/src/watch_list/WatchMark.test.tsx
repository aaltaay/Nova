/**
 * @vitest-environment jsdom
 *
 * The mark beside a ticker on today's hot list (operator, 2026-10-06: "if i star a ticker can we please see
 * 'star' next to it"): a filled ★ for your star, an outline ☆ for an auto star (the top of the Gainers board),
 * nothing for a ticker that is not listed. Watching only -- its title says the bot trades only where Buy / Sell
 * says Bot.
 */
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fakeHotList } from '../hot_list/hotListFake';
import { WatchMark } from './WatchMark';
import { resetWatchListForTests, watchHow } from './watchListStore';

vi.mock('../hot_list', async () => (await import('../hot_list/hotListFake')).hotListFakeModule());
vi.mock('../ux/appDialogApi', () => ({ alertApp: vi.fn(async () => undefined) }));

describe('the hot list mark', () => {
  beforeEach(() => {
    fakeHotList.reset();
    resetWatchListForTests();
  });
  afterEach(cleanup);

  it('says how each ticker is listed: your star, an auto star, or not at all', () => {
    fakeHotList.set(['IPDN', { symbol: 'AIXI', how: 'auto' }]);
    expect(watchHow('ipdn')).toBe('star');
    expect(watchHow('AIXI')).toBe('auto');
    expect(watchHow('QTEX')).toBeNull();
  });

  it('draws a filled ★ for your star and an outline ☆ for an auto star', () => {
    fakeHotList.set(['IPDN', { symbol: 'AIXI', how: 'auto' }]);
    render(<><WatchMark symbol="IPDN" /><WatchMark symbol="AIXI" /><WatchMark symbol="QTEX" /></>);
    const [mine, auto] = screen.getAllByTestId('watch-mark');
    expect(screen.getAllByTestId('watch-mark')).toHaveLength(2);
    expect(mine.dataset.how).toBe('star');
    expect(mine.querySelector('path')?.getAttribute('fill')).toBe('currentColor');
    expect(mine.title).toMatch(/^IPDN is on today's hot list: your star/);
    expect(auto.dataset.how).toBe('auto');
    expect(auto.querySelector('path')?.getAttribute('fill')).toBe('none');
    expect(auto.title).toMatch(/^AIXI was auto-starred onto today's hot list/);
    expect(auto.title).toMatch(/the bot trades it only where its Buy \/ Sell says Bot$/);
  });

  it('appears and goes as the ticker is starred and taken off', () => {
    render(<WatchMark symbol="IPDN" />);
    expect(screen.queryByTestId('watch-mark')).toBeNull();
    act(() => fakeHotList.set(['IPDN']));
    expect(screen.getByTestId('watch-mark').dataset.how).toBe('star');
    act(() => fakeHotList.set([]));
    expect(screen.queryByTestId('watch-mark')).toBeNull();
  });
});
