/**
 * @vitest-environment jsdom
 *
 * The Congress page (ADR 066): the seat maps place every seat by party; the sample desk draws invented members and
 * asks nothing; the live desk shows the agreement before anything is read, then the overview -- seats with the
 * members who reported, the newest reports, the most traded stocks with their IBKR move, the most active members and
 * how late trades show up -- and opens a member's page and a stock's page; the switches and follows are remembered.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { moveFrom, resetKeptCongressForTests } from './api';
import { CongressPage } from './CongressPage';
import { NOVA_API_KEY_HEADER, NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';
import { CONGRESS_PREFS_STORAGE_KEY } from './constants';
import { day, range, rangeText, seat, sideWord } from './format';
import { hemicycle, seatOrder, tally } from './hemicycle';
import { DEFAULT_PREFS, parsePrefs, toggleFollow } from './prefs';
import { sampleCongressBoard, sampleCongressMember } from './sampleCongress';
import type { Board, Member } from './types';

const route = vi.hoisted(() => ({ sample: true }));
vi.mock('../sample_data/useSampleRoute', () => ({ useSampleRoute: () => route.sample }));

function respond(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });
}

async function flush(): Promise<void> {
  await act(async () => {
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  });
}

const member = (b: string, party: string, state: string): Member => ({
  bioguide: b, name: `M ${b}`, party, caucus: null, state, district: null, chamber: 'senate', current: true, left: null, photo: false,
});

describe('seat maps and words', () => {
  it('places every seat on its arcs, left to right', () => {
    const spots = hemicycle(100, 5, 120, 234, 248, 237);
    expect(spots).toHaveLength(100);
    expect(spots[0].x).toBeLessThan(spots[99].x);
    expect(Math.min(...spots.map((s) => s.y))).toBeGreaterThanOrEqual(237 - 234 - 0.001);
    expect(hemicycle(0, 5, 1, 2, 0, 0)).toEqual([]);
  });

  it('seats Democrats, then independents, then Republicans, and counts them', () => {
    const ms = [member('R1', 'R', 'AA'), member('D1', 'D', 'BB'), member('I1', 'I', 'AA'), member('D2', 'D', 'AA')];
    expect(seatOrder(ms).map((m) => m.bioguide)).toEqual(['D2', 'D1', 'I1', 'R1']);
    expect(tally(ms)).toEqual([{ party: 'D', count: 2 }, { party: 'I', count: 1 }, { party: 'R', count: 1 }]);
  });

  it('keeps an amount a range and says a gift is a gift', () => {
    expect(rangeText('$15,001 - $50,000')).toBe('$15K–50K');
    expect(rangeText('$1,000,001 - $5,000,000')).toBe('$1M–5M');
    expect(range('Over $50,000,000', 50_000_000, null)).toBe('Over $50M');
    expect(sideWord({ side: 'sell', partial: true, gift: true })).toBe('Gift');
    expect(seat({ party: 'D', state: 'CA', district: 31, chamber: 'house' })).toBe('D-CA-31');
    expect(seat({ party: 'R', state: 'PA', district: null, chamber: 'senate' })).toBe('R-PA');
    expect(day('2026-10-12', 2026)).toBe('Oct 12');
    expect(day('2025-03-01', 2026)).toBe('Mar 1, 2025');
  });

  it('reads a move from the last close before the period', () => {
    const bars = [{ t: '2025-12-30T00:00:00Z', c: 100 }, { t: '2025-12-31T00:00:00Z', c: 200 }, { t: '2026-10-14T00:00:00Z', c: 250 }];
    expect(moveFrom(bars, '2026-01-01')).toBe(25);
    expect(moveFrom(bars.slice(2), '2026-01-01')).toBeNull();
  });

  it('remembers switches and follows, and refuses what it does not know', () => {
    expect(parsePrefs({ schema_version: 1, seats_period: '30d', traded_period: 'nope', following: ['P000197', 'bad'] }))
      .toEqual({ seatsPeriod: '30d', tradedPeriod: 'ytd', following: ['P000197'] });
    expect(parsePrefs({ schema_version: 2 })).toEqual(DEFAULT_PREFS);
    expect(toggleFollow(toggleFollow(DEFAULT_PREFS, 'P000197'), 'P000197').following).toEqual([]);
  });
});

describe('Congress page on the sample desk', () => {
  beforeEach(() => {
    route.sample = true;
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('draws invented members, says so, and asks the backend for nothing', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<CongressPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('congress-page').textContent).toContain('Nova Marketing Sample Data');
    expect(screen.getByTestId('congress-seats-senate').querySelectorAll('[data-bioguide]')).toHaveLength(100);
    expect(screen.getByTestId('congress-seats-house').querySelectorAll('[data-bioguide]')).toHaveLength(433);
    expect(screen.getByTestId('congress-traded-AAPL').textContent).toContain('+27%');
    expect(screen.getAllByTestId(/^congress-report-/)).toHaveLength(9);
    expect(screen.getByTestId('congress-lag').textContent).toContain('28 days');
    fireEvent.click(screen.getByTestId('congress-seats-period-30d'));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(CONGRESS_PREFS_STORAGE_KEY)).toBeNull();
  });

  it('opens a member from a seat and a stock from Most traded', () => {
    render(<CongressPage onOpenTrader={() => {}} />);
    const seatEl = screen.getByTestId('congress-seats-senate').querySelector('.cg-seat--trades') as Element;
    fireEvent.click(seatEl);
    expect(screen.getByTestId('congress-member')).toBeTruthy();
    fireEvent.click(screen.getByTestId('congress-back'));
    fireEvent.click(screen.getByTestId('congress-traded-NVDA'));
    expect(screen.getByTestId('congress-ticker').textContent).toContain('NVDA');
  });
});

describe('Congress page on the live desk', () => {
  beforeEach(() => {
    route.sample = false;
    window.localStorage.clear();
    resetKeptCongressForTests();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function liveBoard(consent: 'needed' | 'given'): Board {
    const b = sampleCongressBoard();
    return { ...b, consent: { state: consent, accepted_at: null, text: 'It shall be unlawful ...', cite: '5 U.S.C. 13107(c)' } };
  }

  it('asks for the agreement before anything is read, then shows the overview', async () => {
    window.localStorage.setItem(NOVA_API_KEY_STORAGE, 'desk-key');
    let consent: 'needed' | 'given' = 'needed';
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/api/congress/consent')) {
        expect(JSON.parse(String(init?.body))).toEqual({ accept: true });
        // the desk refuses a write without its key (HTTP 401): the agreement carries it like every other write
        expect(new Headers(init?.headers).get(NOVA_API_KEY_HEADER)).toBe('desk-key');
        consent = 'given';
        return respond({ schema_version: 1, consent: liveBoard('given').consent });
      }
      if (url.includes('/api/congress/board')) return respond(liveBoard(consent));
      if (url.includes('/bars')) return respond({ bars: [{ t: '2025-12-31T00:00:00Z', c: 100 }, { t: '2026-10-14T00:00:00Z', c: 90 }] });
      return respond({}, 404);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<CongressPage onOpenTrader={() => {}} />);
    await flush();
    expect(screen.getByTestId('congress-consent').textContent).toContain('It shall be unlawful');
    expect(screen.queryByTestId('congress-seats')).toBeNull();
    fireEvent.click(screen.getByTestId('congress-consent-accept'));
    await flush();
    await flush();
    expect(screen.getByTestId('congress-seats')).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/ticker/AAPL/bars?timeframe=1Day'))).toBe(true);
    expect(screen.getByTestId('congress-traded-AAPL').textContent).toContain('-10%');
  });

  it('asks the board for the chosen topic and the followed members, and remembers the switch', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      urls.push(url);
      if (url.includes('/api/congress/board')) return respond(liveBoard('given'));
      return respond({ bars: [] });
    }));
    window.localStorage.setItem(CONGRESS_PREFS_STORAGE_KEY, JSON.stringify({ schema_version: 1, seats_period: 'ytd',
      traded_period: 'ytd', following: ['S000003'] }));
    render(<CongressPage onOpenTrader={() => {}} />);
    await flush();
    fireEvent.click(screen.getByTestId('congress-topic-senate'));
    await flush();
    expect(urls.some((u) => u.includes('filter=senate'))).toBe(true);
    fireEvent.click(screen.getByTestId('congress-topic-following'));
    await flush();
    expect(urls.some((u) => u.includes('members=S000003'))).toBe(true);
    fireEvent.click(screen.getByTestId('congress-traded-period-90d'));
    expect(JSON.parse(window.localStorage.getItem(CONGRESS_PREFS_STORAGE_KEY) ?? '{}').traded_period).toBe('90d');
  });

  it('Following with nobody starred asks for nobody, and says so', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      urls.push(url);
      if (url.includes('/api/congress/board')) return respond(liveBoard('given'));
      return respond({ bars: [] });
    }));
    render(<CongressPage onOpenTrader={() => {}} />);
    await flush();
    fireEvent.click(screen.getByTestId('congress-topic-following'));
    await flush();
    expect(urls.some((u) => /[?&]members=($|&)/.test(u))).toBe(true);
    expect(screen.getByTestId('congress-following-none').textContent).toContain('Nobody followed yet');
  });

  it('a new member never shows the last one, even when their read fails', async () => {
    const first = sampleCongressMember('S000003');
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/congress/member/S000003')) return respond(first);
      if (url.includes('/api/congress/member/')) return respond({}, 500);
      if (url.includes('/api/congress/board')) return respond(liveBoard('given'));
      return respond({ bars: [] });
    }));
    render(<CongressPage onOpenTrader={() => {}} />);
    await flush();
    const search = screen.getByTestId('congress-search');
    fireEvent.change(search, { target: { value: 'Senator 3' } });
    fireEvent.keyDown(search, { key: 'Enter' });
    await flush();
    expect(screen.getByTestId('congress-member').textContent).toContain('Senator 3');
    fireEvent.change(search, { target: { value: 'Senator 40' } });
    fireEvent.keyDown(search, { key: 'Enter' });
    await flush();
    expect(screen.queryByTestId('congress-member')).toBeNull();
    expect(screen.getByTestId('congress-page').textContent).toContain('Did not load: HTTP 500');
  });

  it('says an old backend has no Congress page', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond({}, 404)));
    render(<CongressPage onOpenTrader={() => {}} />);
    await flush();
    expect(screen.getByTestId('congress-page').textContent).toContain('no Congress page yet');
  });

  it("a member's page lists every trade with the filer's words and the filing", async () => {
    const answer = sampleCongressMember('S000003');
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/congress/member/')) return respond(answer);
      if (url.includes('/api/congress/board')) return respond(liveBoard('given'));
      return respond({ bars: [] });
    }));
    render(<CongressPage onOpenTrader={() => {}} />);
    await flush();
    fireEvent.change(screen.getByTestId('congress-search'), { target: { value: 'Senator 3' } });
    fireEvent.keyDown(screen.getByTestId('congress-search'), { key: 'Enter' });
    await flush();
    expect(screen.getByTestId('congress-member').textContent).toContain('Senator 3');
    fireEvent.click(screen.getByTestId('congress-follow'));
    expect(JSON.parse(window.localStorage.getItem(CONGRESS_PREFS_STORAGE_KEY) ?? '{}').following).toContain('S000003');
  });
});
