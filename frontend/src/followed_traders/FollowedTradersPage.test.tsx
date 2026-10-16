/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetFeedImagesForTests } from './FeedImage';
import { requestFollowedToday, resetFollowedStoresForTests } from './followedStores';
import { resetStreamForTests } from './stream';
import { FOLLOWED_PROOF_HOVER_CLOSE_MS, FOLLOWED_PROOF_HOVER_OPEN_MS } from './constants';
import { closed, day, RECORD, T, trade } from './followedTestData';
import { FollowedTradersPage } from './FollowedTradersPage';
import type { FollowedSlots } from './slots';
import type { FollowedDay } from './types';

type Route = (url: URL) => Response | undefined;

describe('FollowedTradersPage', () => {
  let container: HTMLDivElement;
  let root: Root;
  let asked: string[];

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    asked = [];
    resetFollowedStoresForTests();
    resetStreamForTests();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }));
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    resetFeedImagesForTests();
    vi.unstubAllGlobals();
  });

  async function show(dayAnswer: FollowedDay | (() => Response), extra: Route = () => undefined,
    onOpenTrader?: (symbol: string) => void, slots?: FollowedSlots) {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://desk');
      asked.push(url.pathname + url.search);
      const other = extra(url);
      if (other) return other;
      // A string body: Node 20's fetch cannot read jsdom's Blob ("object.stream is not a function").
      if (url.pathname.endsWith('.jpg')) return new Response('jpeg', { status: 200, headers: { 'content-type': 'image/jpeg' } });
      if (url.pathname === '/api/followed-traders/day') {
        return typeof dayAnswer === 'function' ? dayAnswer() : new Response(JSON.stringify(dayAnswer));
      }
      return new Response('', { status: 404 });
    }));
    await act(async () => {
      root.render(<FollowedTradersPage onOpenTrader={onOpenTrader} slots={slots} />);
    });
    await flush();
  }
  async function flush() {
    for (let i = 0; i < 4; i += 1) await act(async () => { await Promise.resolve(); });
  }
  const q = (id: string) => container.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const click = async (el: Element | null) => {
    await act(async () => { (el as HTMLElement).click(); });
    await flush();
  };
  const hover = async (el: Element, type: 'mouseover' | 'mouseout', ms: number) => {
    await act(async () => {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, relatedTarget: document.body }));
      await new Promise((r) => setTimeout(r, ms));
    });
    await flush();
  };
  const card = (id: string) => document.querySelector(`[data-testid="ft-proof-card-${id}"]`) as HTMLElement | null;

  it("labels each slot with the read's time when the feed reads the stream's past, never 'now'", async () => {
    await show(day({ capture: { ...day().capture!, clock: '09:40:00', traders: ['ALPHA'] } }));
    expect(q('ft-capture-pill')!.textContent).toMatch(/^Reading 30m 00s behind the stream/);
    expect(q('ft-slot-ALPHA')!.querySelector('figcaption')!.textContent).toBe('Their slot as last read · 09:40:00 ET');
  });

  it('says when they left as a window when the bar was not read between their last sighting and the next', async () => {
    // 2026-10-15: a feed restart read nothing for ten minutes while the morning show ended.
    const d = day();
    const left = T + 120;
    const gone = { ...d.traders[0], seen: { last_ts: left - 600, left_ts: left }, open: [] };
    await show({ ...d, capture: { ...d.capture!, traders: ['BRAVO'] }, traders: [gone, d.traders[1]] });
    expect(q('ft-left-ALPHA')!.textContent).toBe('Left the bar 09:52:00–10:02:00');
  });

  it('shows a trader who left the bar with every trade closed when they left, marked off air', async () => {
    // Operator, 2026-10-14: ALPHA's show ended at 11:00 with BAC on the bar, and the page still said Holding now;
    // "if they are off air then all trades are closed!"
    const d = day();
    const alpha = d.traders[0];
    const left = T + 120;
    const gone = { ...alpha, seen: { last_ts: left, left_ts: left }, open: [],
      record: { ...alpha.record, open: 0, losses: 1, win_rate: 50 },
      closed: [{ ...alpha.open[0], status: 'closed' as const, left_bar: true, result: 'loss' as const,
        now: null, pl: { per_share: -0.1, pct: -5 }, held: { min_sec: 120, max_sec: 120 },
        exit: { state: 'at' as const, price: 1.9, low: null, high: null, from_ts: null, to_ts: left, trade_ts: left - 1,
          source: 'ibkr_trades' as const, why: null } }, ...alpha.closed] };
    await show({ ...d, capture: { ...d.capture!, traders: ['BRAVO'] }, traders: [gone, d.traders[1]] });
    expect(q('ft-left-ALPHA')!.textContent).toBe('Left the bar 10:02:00');
    expect(q('ft-trader-ALPHA')!.textContent).not.toContain('Off air');
    expect(q('ft-trader-ALPHA')!.querySelector('.ft-closed--open')).toBeNull();
    const row = q('ft-row-o1')!;
    expect(row.tagName).toBe('TR');
    expect(row.textContent).toContain('LOSS');
    expect(q('ft-off-air-close-o1')!.textContent).toBe('off air');
    // BRAVO is on the bar: as before.
    expect(q('ft-trader-BRAVO')!.textContent).toContain('On air');
    // Its exit has a time but no picture of a close: both proofs say why (review of PR #954).
    await hover(q('ft-proof-o1')!, 'mouseover', FOLLOWED_PROOF_HOVER_OPEN_MS + 30);
    expect(card('o1')!.textContent).toContain('Closed when they left the bar');
    expect(card('o1')!.querySelector('img[alt="ALPHA\'s position bar at the exit"]')).toBeNull();
    await click(card('o1'));
    expect(q('ft-proof')!.textContent).toContain('Closed when they left the bar');
    expect(q('ft-proof')!.querySelector('img[alt="ALPHA\'s position bar at the exit"]')).toBeNull();
  });

  it('says the feed is not configured on a 404, never an empty list', async () => {
    await show(() => new Response('', { status: 404 }));
    expect(q('ft-state')!.textContent).toMatch(/not configured/);
  });

  it('says the feed is down with its reason in the pill', async () => {
    await show(day({ feed: { state: 'unreachable', error: 'timed out after 3 s' }, traders: [], capture: null,
      prices: null, overall: null, dates: [] }));
    expect(q('ft-capture-pill')!.textContent).toBe('The feed is not answering · timed out after 3 s');
    expect(q('ft-trader-ALPHA')).toBeNull();
  });

  it('draws each trader: their card, one table with the open positions on top and closed rows by result, and the activity', async () => {
    await show(day({ capture: { ...day().capture!, traders: ['ALPHA'] } }));
    expect(q('ft-capture-pill')!.textContent).toBe('Live · 6s behind the stream · bar read 10:09:54 ET');
    // The bar's read is on the slot; the slot is the live one while capture reads the bar.
    expect(q('ft-slot-ALPHA')!.getAttribute('title')).toBe('Read as: LONG ABCD 2.00');
    expect(q('ft-slot-ALPHA')!.querySelector('figcaption')!.textContent).toBe('Their slot now');
    // No live image for BRAVO: their newest evidence stands in, with its time.
    expect(q('ft-slot-BRAVO')!.textContent).toContain('Their slot at their last open or close · 09:59:00 ET');
    expect(q('ft-trader-ALPHA')!.textContent).toContain('On air');
    expect(q('ft-trader-BRAVO')!.textContent).toContain('Off air');
    expect(q('ft-record-ALPHA')!.textContent).toContain('1W / 0L · 1 open · Win rate 100%');
    // Operator, 2026-10-15, of the OPEN tiles: "make this more compact". One table: open rows first, striped blue.
    expect(q('ft-trader-ALPHA')!.querySelector('.ft-trades__head')!.textContent).toMatch(/^Trades today21 open · 1 won · 0 lost/);
    const tile = q('ft-row-o1')!;
    expect(tile.tagName).toBe('TR');
    expect(tile.className).toContain('ft-closed--open');
    expect(tile.parentElement!.firstElementChild).toBe(tile);
    expect(tile.textContent).toContain('OPEN');
    expect(tile.textContent).toContain('2.00 → 2.50now');
    expect(tile.textContent).toContain('+0.50');
    // An open position's dollars are from the price now, a closed trade's from when it left their bar (review).
    expect(tile.querySelector('.ft-pl')!.getAttribute('data-tip')).toContain('IBKR’s last price now');
    const win = q('ft-row-c1')!;
    expect(win.querySelector('.ft-pl')!.getAttribute('data-tip')).toContain('when it left their bar');
    expect(win.className).toContain('ft-closed--win');
    expect(win.textContent).toContain('WIN');
    expect(win.textContent).toContain('2.00 → 2.20');
    const range = q('ft-row-c2')!;
    expect(range.className).toContain('ft-closed--unscored');
    expect(range.textContent).toContain('by 09:40:00');
    expect(range.textContent).toContain('77.10–77.90 est.');
    expect(range.textContent).toContain('UNSCORED');
    expect(q('ft-trader-BRAVO')!.querySelector('.ft-closed--open')).toBeNull();
    // The Activity is one line per event: no screenshots.
    expect(q('ft-activity')!.textContent).toContain('ALPHA closed');
    expect(q('ft-activity')!.querySelector('img[alt*="position bar"]')).toBeNull();
    expect(asked).toContain('/api/followed-traders/live/ALPHA.jpg');
    expect(asked).toContain('/api/followed-traders/faces/2026-10-13/ALPHA.jpg');
  });

  it('never prices a ticker that may be glued to its price, and marks one IBKR put back', async () => {
    // The bar's "XYZI 14.03" read XYZ 114.03 (made-up stocks, both near $14): until IBKR's tape at the entry says
    // which, no P/L, never the +87% short XYZ at 114.03 would show.
    const ticker = { read_symbol: 'XYZ', read_price: 114.03, other_symbol: 'XYZI', other_price: 14.03 };
    const answer = day();
    answer.traders[0].open = [trade({ id: 'g1', symbol: 'XYZ', side: 'short',
      entry: { first_price: 114.03, avg_price: 114.03, ts: T, since_ts: null, known: true },
      now: { state: 'no_line', price: null, trade_ts: null, why: 'neither fits' },
      ticker: { ...ticker, state: 'unchecked', why: 'the bar read XYZ 114.03; IBKR at the entry: XYZ 14.00, XYZI 16.40: neither fits' } })];
    answer.traders[0].closed = [closed({ id: 'g2', symbol: 'XYZI', side: 'short',
      ticker: { ...ticker, state: 'corrected', why: 'the bar read XYZ 114.03; IBKR at the entry: XYZ 14.00, XYZI 14.05: the ticker was read glued to its price' } })];
    await show(answer);
    const tile = q('ft-row-g1')!;
    expect(q('ft-ticker-check-g1')!.textContent).toBe('ticker check');
    expect(tile.textContent).not.toMatch(/%/);
    expect(tile.querySelector('[data-testid="ft-ticker-mark"]')!.textContent).toBe('?');
    const row = q('ft-row-g2')!;
    expect(row.textContent).toContain('XYZI');
    expect(row.querySelector('[data-testid="ft-ticker-mark"]')!.textContent).toBe('fixed');
    expect(q('ft-activity')!.querySelectorAll('[data-testid="ft-ticker-mark"]').length).toBeGreaterThan(0);
  });

  it('opens a ticker in the Trader: an open row, a closed row and a proof', async () => {
    const opened = vi.fn();
    await show(day(), () => undefined, opened);
    await click(q('ft-row-o1')!.querySelector('.ft-ticker-link'));
    await click(q('ft-row-c1')!.querySelector('.ft-ticker-link'));
    expect(opened.mock.calls).toEqual([['ABCD'], ['EFGH']]);
    expect(q('ft-proof')).toBeNull();
    await click(q('ft-proof-c1'));
    await click(q('ft-proof')!.querySelector('.ft-ticker-link'));
    expect(opened).toHaveBeenLastCalledWith('EFGH');
  });

  it('draws the ticker as plain text when the desk gives the page no Trader', async () => {
    await show(day());
    expect(q('ft-row-o1')!.querySelector('.ft-ticker-link')).toBeNull();
    expect(q('ft-row-o1')!.querySelector('.ft-ticker')!.textContent).toBe('ABCD');
  });

  it('draws what another feature gives it: after the title, in a card on today, beside an open row', async () => {
    // Bots > LiveTrader Bots (operator, 2026-10-15): the LiveTrader Bots key, each host's bot, a copy's chip.
    const slots: FollowedSlots = {
      Head: () => <span data-testid="slot-head">key</span>,
      Trader: ({ name, open }) => <span data-testid={`slot-trader-${name}`}>{open.map((t) => t.symbol).join(',')}</span>,
      OpenBadge: ({ trade }) => <span data-testid={`slot-badge-${trade.id}`}>BOT</span>,
    };
    await show(day(), () => undefined, undefined, slots);
    expect(q('slot-head')!.previousElementSibling!.textContent).toBe('LiveTrader Bots');
    const card = q('ft-trader-ALPHA')!.querySelector('.ft-trader__card')!;
    expect(card.className).toContain('ft-trader__card--slot');
    expect(q('slot-trader-ALPHA')!.textContent).toBe('ABCD');
    expect(q('slot-trader-ALPHA')!.previousElementSibling!.className).toBe('ft-trader__who');
    expect(q('slot-trader-BRAVO')!.textContent).toBe('');
    expect(q('ft-row-o1')!.querySelector('[data-testid="slot-badge-o1"]')).toBeTruthy();
    expect(q('ft-row-c1')!.querySelector('[data-testid^="slot-badge"]')).toBeNull();
  });

  it('draws no card slot and no row chip on a past day: the bots are now, not then', async () => {
    const slots: FollowedSlots = {
      Trader: ({ name }) => <span data-testid={`slot-trader-${name}`} />,
      OpenBadge: ({ trade }) => <span data-testid={`slot-badge-${trade.id}`} />,
    };
    const past = day({ date: '2026-10-12' });
    await show(past, () => undefined, undefined, slots);
    expect(q('slot-trader-ALPHA')).toBeNull();
    expect(q('slot-badge-o1')).toBeNull();
    expect(q('ft-trader-ALPHA')!.querySelector('.ft-trades__head')!.textContent).toMatch(/^Trades21 open/);
    expect(q('ft-row-o1')!.textContent).not.toContain('now');
  });

  it('opens an Activity event’s stock in the Trader', async () => {
    const opened = vi.fn();
    await show(day(), () => undefined, opened);
    expect(q('ft-activity')!.textContent).toContain('click an event to open it in the Trader');
    await click(container.querySelector('[data-testid="ft-activity-c1|out"]'));
    expect(opened).toHaveBeenCalledWith('EFGH');
    expect(q('ft-proof')).toBeNull();
  });

  it('opens an Activity event on its trade’s proof when the desk gives the page no Trader', async () => {
    await show(day());
    expect(q('ft-activity')!.textContent).toContain('click an event for its Proof');
    await click(container.querySelector('[data-testid="ft-activity-c1|out"]'));
    expect(q('ft-proof')).not.toBeNull();
  });

  it('gives a trader on the bar with no trade that day their card, with the bar slot’s photo', async () => {
    const d = day();
    d.capture!.bar = [...d.capture!.bar!, { trader: 'CHARLIE', positions: [], image: null,
      face: '/api/followed-traders/faces/2026-10-13/CHARLIE.jpg' }];
    await show(d);
    expect(q('ft-record-CHARLIE')!.textContent).toBe('no trades today');
    expect(asked).toContain('/api/followed-traders/faces/2026-10-13/CHARLIE.jpg');
  });

  it('plays the stream the feed reads, closes it, and Watch live brings it back', async () => {
    await show(day({ capture: { ...day().capture!, video_id: 'R5YIugCJar0' } }));
    const frame = q('ft-stream-frame') as HTMLIFrameElement;
    expect(frame.src).toBe('https://www.youtube.com/embed/R5YIugCJar0?autoplay=1&mute=1&playsinline=1&rel=0&enablejsapi=1');
    expect(q('ft-stream')!.textContent).toContain('LIVE');
    await click(q('ft-stream-close'));
    expect(q('ft-stream')).toBeNull();
    await click(q('ft-watch-live'));
    expect(q('ft-stream')).not.toBeNull();
  });

  it('plays no past broadcast: off air the player keeps its place and shows OFFLINE with why', async () => {
    // The operator's 2026-10-13 evening: the feed's last status still names the day's stream as live, 5 h stale.
    await show(day({ capture: { ...day().capture!, video_id: 'R5YIugCJar0', clock: '15:57:12', age_sec: 18_000 } }));
    const player = q('ft-stream')!;
    expect(player.getAttribute('data-on-air')).toBe('false');
    expect(q('ft-stream-frame')).toBeNull();
    expect(q('ft-stream-offline')!.textContent).toContain('Offline');
    expect(q('ft-stream-off-why')!.textContent).toBe('last read 15:57:12 ET');
    // Nothing that reaches the ended broadcast: no sound, Pop out or YouTube link; close stays.
    for (const id of ['ft-stream-sound', 'ft-stream-popout', 'ft-stream-youtube', 'ft-stream-reload']) expect(q(id)).toBeNull();
    expect(player.textContent).toContain('Last stream: Morning show');
    const watch = q('ft-watch-live') as HTMLButtonElement;
    expect(watch.disabled).toBe(true);
    expect(watch.getAttribute('data-why')).toBe('Offline · last read 15:57:12 ET');
    expect(q('ft-head-video')!.textContent).toBe('Last stream: Morning show');
    await click(q('ft-stream-close'));
    expect(q('ft-stream')).toBeNull();
  });

  it('turns the stream OFFLINE when the backend stops answering, never playing on from a kept answer', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
    try {
      let down = false;
      await show(() => {
        if (down) throw new TypeError('Failed to fetch');
        return new Response(JSON.stringify(day({ capture: { ...day().capture!, video_id: 'R5YIugCJar0' } })));
      });
      expect(q('ft-stream-frame')).not.toBeNull();
      down = true;
      await act(async () => { vi.advanceTimersByTime(62_000); });
      await flush();
      expect(q('ft-stream-frame')).toBeNull();
      expect(q('ft-stream-offline')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('says when today resets: 04:00 ET, the desk’s own day', async () => {
    const resetsAt = Date.UTC(2026, 9, 14, 8, 0, 0) / 1000; // 04:00 ET, 2026-10-14
    await show(day({ resets_at: resetsAt }));
    const reset = q('ft-day-reset')!;
    expect(reset.textContent).toBe('Resets 4:00 AM ET');
    expect(reset.getAttribute('data-tip')).toContain('Today runs until 4:00 AM ET on Wed, Oct 14, the premarket');
  });

  it("shows the hosts only: the Live Trader bots live under Bots > LiveTrader Bots (2026-10-15)", async () => {
    await show(day());
    await flush();
    expect(q('bots-live-traders')).toBeNull();
    expect(asked.some(path => path.startsWith('/api/bot/live-traders'))).toBe(false);
    expect(container.textContent).not.toMatch(/Bot switch is off/);
  });

  it('names no reset on a past day', async () => {
    await show(day({ date: '2026-10-09', resets_at: Date.UTC(2026, 9, 14, 8, 0, 0) / 1000 }));
    expect(q('ft-day-reset')).toBeNull();
  });

  it('keeps the stream on a past day: it is the feed’s now, whatever day is shown', async () => {
    await show(day({ date: '2026-10-09', capture: { ...day().capture!, video_id: 'R5YIugCJar0' } }));
    expect((q('ft-watch-live') as HTMLButtonElement).disabled).toBe(false);
    expect(q('ft-stream')).not.toBeNull();
  });

  it('says why Watch live is off when the feed names no stream', async () => {
    await show(day());
    const watch = q('ft-watch-live') as HTMLButtonElement;
    expect(watch.disabled).toBe(true);
    expect(watch.getAttribute('data-why')).toBe('The feed has not named a stream it reads yet');
    expect(q('ft-stream')).toBeNull();
  });

  it('says why open positions are not priced', async () => {
    const d = day({ prices: { state: 'ibkr_down', why: 'IBKR is not connected' } });
    d.traders[0].open[0].now = { state: 'off', price: null, trade_ts: null, why: 'IBKR is not connected' };
    await show(d);
    expect(q('ft-prices')!.textContent).toBe('Prices now: IBKR is not connected');
  });

  it('shows a trade’s screenshots when Proof is hovered, and the whole Proof on a click of the card', async () => {
    await show(day());
    await hover(q('ft-proof-c1')!, 'mouseover', FOLLOWED_PROOF_HOVER_OPEN_MS + 30);
    const peek = card('c1')!;
    expect(peek.textContent).toContain('ALPHA');
    // The screenshots load after the card shows.
    await act(async () => {
      await vi.waitFor(() => {
        expect(peek.querySelector('img[alt="ALPHA\'s position bar at the entry"]')).not.toBeNull();
        expect(peek.querySelector('img[alt="ALPHA\'s position bar at the exit"]')).not.toBeNull();
      });
    });
    expect(q('ft-proof')).toBeNull(); // the board stays
    await hover(q('ft-proof-c1')!, 'mouseout', FOLLOWED_PROOF_HOVER_CLOSE_MS + 30);
    expect(card('c1')).toBeNull();
    // Opened by the pointer, focus stays elsewhere: Escape still closes it.
    await hover(q('ft-proof-c1')!, 'mouseover', FOLLOWED_PROOF_HOVER_OPEN_MS + 30);
    expect(document.activeElement).not.toBe(q('ft-proof-c1'));
    await act(async () => { document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
    expect(card('c1')).toBeNull();
    // An open position has no exit screenshot yet: the card says so.
    await hover(q('ft-proof-o1')!, 'mouseover', FOLLOWED_PROOF_HOVER_OPEN_MS + 30);
    expect(card('o1')!.textContent).toContain('Still open');
    await click(card('o1'));
    expect(q('ft-proof')).not.toBeNull();
    expect(card('o1')).toBeNull();
  });

  it('opens a trade’s proof with what was read and the reads ignored', async () => {
    const reads = {
      schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, date: '2026-10-13', trader: 'ALPHA',
      available: true, why: null, truncated: false,
      reads: [
        { ts: T - 600, until_ts: T - 500, seen: true, unparsed: [], positions: [{ side: 'long', symbol: 'EFGH', price: 2 }] },
        { ts: T - 500, until_ts: T - 498, seen: true, unparsed: [], positions: [{ side: 'long', symbol: 'EFG', price: 12 }] },
        { ts: T - 498, until_ts: T + 300, seen: true, unparsed: [], positions: [{ side: 'long', symbol: 'EFGH', price: 2 }] },
        { ts: T + 300, until_ts: null, seen: true, unparsed: [], positions: [] },
      ],
    };
    await show(day(), (url) => url.pathname === '/api/followed-traders/reads'
      ? new Response(JSON.stringify(reads)) : undefined);
    await click(q('ft-proof-c1'));
    const proof = q('ft-proof')!;
    expect(proof.textContent).toContain('EFGH 2.00 new');
    expect(proof.textContent).toContain('EFGH 2.00 gone');
    expect(proof.textContent).toContain('1 read during this trade differed from what was logged and was ignored');
    expect(proof.textContent).not.toMatch(/drop this trade/i);
    expect(asked.some((a) => a.startsWith('/api/followed-traders/reads?date=2026-10-13&trader=ALPHA'))).toBe(true);
    await click(q('ft-proof-back'));
    expect(q('ft-proof')).toBeNull();
  });

  it('asks the record for Week, and the day’s own for Day', async () => {
    const week = { schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, range: 'week',
      from: '2026-10-07', to: '2026-10-13', dates: [], pending: 2,
      overall: { wins: 5, losses: 2, scratches: 0, unscored: 1, open: 1, win_rate: 71.4 },
      traders: [{ name: 'ALPHA', record: { wins: 4, losses: 1, scratches: 0, unscored: 0, open: 1, win_rate: 80 } }] };
    await show(day(), (url) => url.pathname === '/api/followed-traders/record' ? new Response(JSON.stringify(week)) : undefined);
    await click(q('ft-range-week'));
    expect(asked).toContain('/api/followed-traders/record?range=week&date=2026-10-13');
    expect(q('ft-record-ALPHA')!.textContent).toContain('4W / 1L · 1 open · Win rate 80%');
    expect(q('ft-record-everyone')!.textContent).toContain('Win rate 71.4%');
    expect(q('ft-records')!.textContent).toContain('2 exits still being read from IBKR');
  });

  it('shows what each trader and everyone made at $1,000 a trade, leaving unscored trades out', async () => {
    // Operator ask 2026-10-14: "we can see the PL per share in terms of percentage"; their pick, "Added up"; then
    // 2026-10-15: "Show the P/L as dollars at $1,000 a trade, with the cents per share and % under each trade".
    await show(day());
    const alpha = q('ft-pl-ALPHA')!;
    expect(alpha.textContent).toBe('+$100.00copied at $1,000 a trade · 1 trade');
    expect(alpha.className).toContain('ft-plfig--up');
    expect(alpha.querySelector('svg.ft-spark')).not.toBeNull();
    expect(alpha.getAttribute('data-tip')).toContain('What copying 1 closed trade with $1,000 each would have made');
    expect(alpha.getAttribute('data-tip')).toContain('the feed never shows their size');
    // BRAVO's only trade is unscored: a dash that says why, never $0.
    const bravo = q('ft-pl-BRAVO')!;
    expect(bravo.textContent).toBe('—P/L copied at $1,000 a trade');
    expect(bravo.getAttribute('data-tip')).toContain('No closed trade with one known exit price');
    expect(bravo.getAttribute('data-tip')).toContain('Left out: 1 unscored trade');
    expect(q('ft-pl-everyone')!.textContent).toBe('+$100.00');
  });

  it('adds up a Week from the record’s scored trades, and says when a backend sends none', async () => {
    const week = { schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, range: 'week',
      from: '2026-10-07', to: '2026-10-13', dates: [], pending: 0,
      overall: { wins: 2, losses: 1, scratches: 0, unscored: 1, open: 0, win_rate: 66.7 },
      traders: [
        { name: 'ALPHA', record: { wins: 2, losses: 0, scratches: 0, unscored: 0, open: 0, win_rate: 100 },
          scored: [{ ts: T - 900, pct: 1.25 }, { ts: T - 300, pct: 0.5 }] },
        { name: 'BRAVO', record: { wins: 0, losses: 1, scratches: 0, unscored: 1, open: 0, win_rate: 0 },
          scored: [{ ts: T - 600, pct: -0.4 }] },
      ] };
    let answer: object = week;
    await show(day(), (url) => url.pathname === '/api/followed-traders/record' ? new Response(JSON.stringify(answer)) : undefined);
    await click(q('ft-range-week'));
    expect(q('ft-pl-ALPHA')!.textContent).toBe('+$17.50copied at $1,000 a trade · 2 trades');
    expect(q('ft-pl-BRAVO')!.textContent).toBe('−$4.00copied at $1,000 a trade · 1 trade');
    expect(q('ft-pl-BRAVO')!.className).toContain('ft-plfig--down');
    expect(q('ft-pl-everyone')!.textContent).toBe('+$13.50');
    answer = { ...week, traders: week.traders.map(({ name, record }) => ({ name, record })) };
    await click(q('ft-range-all'));
    expect(q('ft-pl-ALPHA')!.textContent).toBe('—P/L copied at $1,000 a trade');
    expect(q('ft-pl-everyone')!.getAttribute('data-tip')).toContain('restart it on the desk’s release');
  });

  it('steps to the previous day and opens the calendar with a preview', async () => {
    await show(day());
    expect((q('ft-next-day') as HTMLButtonElement).disabled).toBe(true);
    expect(q('ft-next-day')!.getAttribute('data-why')).toBeTruthy();
    await click(q('ft-day-button'));
    expect(q('ft-day-picker')).not.toBeNull();
    expect((q('ft-day-2026-10-14') as HTMLButtonElement).disabled).toBe(true);
    await click(q('ft-day-2026-10-09'));
    expect(asked).toContain('/api/followed-traders/day?date=2026-10-09&quotes=0');
    await click(q('ft-prev-day'));
    expect(asked).toContain('/api/followed-traders/day?date=2026-10-09');
  });

  it('shows each day’s result in its square and each trader’s in the preview, copied at $1,000 a trade', async () => {
    // Operator ask 2026-10-15: "i wanna see the result of each for each day", "and the price in each square".
    const all = { schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, range: 'all', from: null,
      to: '2026-10-13', dates: ['2026-10-09', '2026-10-13'], pending: 0, overall: null,
      traders: [{ name: 'ALPHA', record: RECORD, scored: [
        { ts: T, pct: 12.5, date: '2026-10-09' }, { ts: T + 9, pct: -3, date: '2026-10-13' }] }] };
    await show(day(), (url) => (url.pathname === '/api/followed-traders/record'
      ? new Response(JSON.stringify(all)) : undefined));
    await click(q('ft-day-button'));
    expect(asked).toContain('/api/followed-traders/record?range=all&date=2026-10-13');
    const sq = q('ft-day-pl-2026-10-09')!;
    expect(sq.textContent).toBe('+$125');
    expect(sq.className).toContain('ft-day__pl--up');
    expect(q('ft-day-pl-2026-10-13')!.textContent).toBe('−$30');
    await click(q('ft-day-2026-10-09'));
    expect(q('ft-preview-pl-ALPHA')!.textContent).toBe('+$125.00');
  });

  it('goes back to today when a toast asks, whatever past day it was showing', async () => {
    const resetsAt = Date.UTC(2026, 9, 14, 8, 0, 0) / 1000;
    await show(day({ resets_at: resetsAt }), (url) => {
      const date = url.searchParams.get('date');
      if (url.pathname !== '/api/followed-traders/day' || !date) return undefined;
      return new Response(JSON.stringify(day({ date, resets_at: resetsAt })));
    });
    await click(q('ft-prev-day'));
    expect(q('ft-day-reset')).toBeNull();
    await act(async () => { requestFollowedToday(); });
    await flush();
    expect(q('ft-day-reset')).not.toBeNull();
  });
});
