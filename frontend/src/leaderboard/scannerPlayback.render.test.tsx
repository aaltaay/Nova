/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ScannerTabPanels } from '../components/ScannerTabPanels';
import { ScannerBoardHeader } from '../scanner/ScannerBoardHeader';
import { ScannerDataContextProvider, makeLiveScannerFeedStub } from '../scanner/ScannerDataContext';
import type { HealthStatus } from '../types/health';
import type { ScannerRow } from '../types/scanner';
import { LEADERBOARD_CATALYSTS_IN_NEWS_COLUMN } from './leaderboardConstants';
import { parseLeaderboardAt } from './leaderboardParse';
import { replayFromAnswer } from './leaderboardRows';
import { withScannerReplay } from './scannerReplayFeed';

vi.mock('../components/useScannerRowFacts', () => ({
  useScannerRowFacts: () => ({ recording: false, allowlisted: false, depthHeld: false }),
}));
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({ symbols: [], isAllowed: () => false, add: vi.fn(), remove: vi.fn(), refresh: vi.fn() }),
}));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: 'sim', connected: true }) }));

const epoch = (time: string) => Date.parse(`2026-09-21T${time}-04:00`) / 1000;
const M = epoch('07:42:00');

const answer = (over: Record<string, unknown> = {}) => parseLeaderboardAt({
  date: '2026-09-21', source: 'recorded', minute_ts: M, covered: true, gap: null,
  boards: { gainers: { state: 'live', rows: [
    { symbol: 'GRML', rank: 1, price: 9.27, prev_close: null, change_pct: null, volume: null, rvol: 6.1,
      rvol_basis: 'time_of_day_20', halted: true, has_news: null },
  ] } },
  leaders: { symbols: ['GRML'] },
  ...over,
});

const LIVE_ROW = { symbol: 'LIVE', price: 1, prev_close: 1, change_pct: 0, change_abs: 0, gap_percent: 0, volume: 1,
  rel_volume: null, has_news: false, newest_headline_at: null, market_cap: null, float: null,
  short_interest: null, short_ratio: null } as ScannerRow;

function Board({ replay, tab = 'gainers' }: {
  replay: ReturnType<typeof replayFromAnswer> | null;
  tab?: 'gainers' | 'catalysts';
}) {
  const feed = withScannerReplay(makeLiveScannerFeedStub({ gainers: [LIVE_ROW] }), replay);
  return (
    <ScannerDataContextProvider value={feed}>
      <ScannerBoardHeader title="Gainers" filters={null} scannedAgoSec={5} />
      <ScannerTabPanels
        activeTab={tab} mode="market" health={{ status: 'connected', latency_ms: 1 } as HealthStatus}
        discoveryProvider="ibkr" gappers={feed.gappers} gainers={feed.gainers} losers={feed.losers}
        afterhours={feed.afterhours} largeCap={feed.largeCap} catalysts={feed.catalysts} watchlistEntries={[]}
        selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} pricesStale={false} flashSymbols={{}}
      />
    </ScannerDataContextProvider>
  );
}

afterEach(() => cleanup());

describe('the Scanner board at the Sim playhead', () => {
  it('Live / Paper / live edge: the live rows and the live session line, unchanged', () => {
    render(<Board replay={null} />);
    expect(screen.getByText('LIVE')).toBeTruthy();
    expect(screen.queryByTestId('scanner-board-replay')).toBeNull();
    expect(screen.getByTestId('scanner-board-phase')).toBeTruthy();
  });

  it('shows the recorded board, labelled, with unknowns as dashes and the halt marked', () => {
    render(<Board replay={replayFromAnswer('2026-09-21', M, answer())} />);
    expect(screen.getByTestId('scanner-board-replay').textContent).toBe('Sim · 2026-09-21 07:42 ET · recorded');
    expect(screen.queryByTestId('scanner-board-phase')).toBeNull();
    expect(screen.queryByText('LIVE')).toBeNull();
    expect(screen.getByText('GRML')).toBeTruthy();
    expect(screen.getByTestId('scanner-row-halted').textContent).toBe('HALTED');
    const prevClose = document.querySelector('td[data-col="prev_close"]')?.textContent ?? '';
    expect(prevClose).not.toMatch(/0\.00/);
    const volume = document.querySelector('td[data-col="volume"]') as HTMLElement;
    expect(volume.querySelector('[data-rvol-source="time_of_day_20"]')).toBeTruthy();
    expect(volume.getAttribute('title') ?? volume.querySelector('[title]')?.getAttribute('title')).toMatch(/Time-of-day RVOL/);
  });

  it('labels a rebuilt board "rebuilt"', () => {
    const rebuilt = answer({
      source: 'reconstructed', boards: { market: { state: 'rebuilt', rows: [{ symbol: 'MKT', rank: 1, price: 4 }] } },
    });
    render(<Board replay={replayFromAnswer('2026-09-18', M, rebuilt)} />);
    expect(screen.getByTestId('scanner-board-replay').textContent).toBe('Sim · 2026-09-18 07:42 ET · rebuilt');
    expect(screen.getByText('MKT')).toBeTruthy();
  });

  it('shows a mover\'s catalyst at the playhead in the News column, aged from the playhead', () => {
    const withVerdict = answer({ at: M + 20, catalyst_symbols: 1, boards: { gainers: { state: 'live', rows: [
      { symbol: 'GRML', rank: 1, price: 9.27, catalyst: {
        verdict: 'catalyst', category: 'fda_regulatory', strength: 'strong', title: 'Acme Receives FDA Approval',
        source: 'alpaca', published_ts: M - 580, url: null, negative_too: false, rules_version: 'v6',
        sources_answered: ['alpaca'], n_items: 1, news_pending: false, halt_code: null,
      } },
    ] } } });
    render(<Board replay={replayFromAnswer('2026-09-21', M, withVerdict)} />);
    const mark = document.querySelector('td[data-col="newest_headline_at"] [data-news-mark]');
    expect(mark?.getAttribute('data-news-mark')).toBe('catalyst');
    // Ten minutes old at the playhead -- not days old by the wall clock.
    expect(mark?.className).toMatch(/flame-hot/);
    expect(mark?.getAttribute('title')).toMatch(/Acme Receives FDA Approval/);
    expect(mark?.getAttribute('title')).toMatch(/10m ago/);
  });

  it('the Catalysts tab points at the News column on a day with catalysts on file', () => {
    render(<Board tab="catalysts" replay={replayFromAnswer('2026-09-21', M, answer({ catalyst_symbols: 3 }))} />);
    expect(screen.getByText(LEADERBOARD_CATALYSTS_IN_NEWS_COLUMN)).toBeTruthy();
  });

  it('in a gap: the reason and its times, and no rows', () => {
    const gap = answer({ covered: false, gap: { reason: 'feed_down', start: epoch('09:12:00'), end: epoch('09:31:00') } });
    render(<Board replay={replayFromAnswer('2026-09-21', epoch('09:20:00'), gap)} />);
    expect(screen.getByTestId('scanner-board-replay-gap').textContent).toBe('No board: IBKR feed down 09:12-09:31');
    expect(screen.getByTestId('scanner-replay-absence').textContent).toBe('No board: IBKR feed down 09:12-09:31');
    expect(document.querySelector('table')).toBeNull();
    expect(screen.queryByText('LIVE')).toBeNull();
  });
});
