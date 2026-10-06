/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PROPOSAL_DISMISSED_KEY } from '../constantGroups/setups';
import { ORDER_TICKET_PREFILL_EVENT, type OrderTicketPrefill } from '../ibkr/orderTicketPrefill';
import { confirmDeskVenue, _resetConfirmedDeskVenueStoreForTests } from '../ibkr/confirmedDeskVenueStore';
import { SAMPLE_SETUPS_BOARD, SAMPLE_SETUPS_SCOREBOARD } from '../sample_data/sampleSetups';
import { _resetDismissedForTests, dismiss, isDismissed, parseDismissed } from './proposalDismissals';
import { SetupsAlertCard } from './SetupsAlertCard';
import { SetupsBoard } from './SetupsBoard';
import { SetupsPanel } from './SetupsPanel';
import { SetupsScoreboard } from './SetupsScoreboard';
import { resetSetupsBoardFilterForTests } from './setupsBoardFilter';
import { _resetSleeveForTests, type SleeveRisk } from './sleeveRisk';
import type { SetupProposal, SetupsBoard as Board } from './types';

const openStockView = vi.fn();
vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => ({ openStockView }) }));
const stream = vi.hoisted(() => ({ value: null as null | { board: unknown; connected: boolean } }));
vi.mock('./SetupsStreamContext', () => ({ useSetupsBoard: () => stream.value }));

const WITH_PROPOSAL: Board = {
  ...SAMPLE_SETUPS_BOARD,
  proposals: SAMPLE_SETUPS_BOARD.rows.flatMap(r => (r.proposal ? [r.proposal] : [])),
};

/** The Paper sleeve's $20 risk per trade, as the board reads it. */
const RISK: SleeveRisk = {
  riskUsd: 20, source: 'sleeve', venue: 'paper', why: null, ttlSec: 3, bounds: [1, 10_000], saving: false,
  saveError: null, moveError: null,
};

function captureStaged(): { staged: OrderTicketPrefill[]; stop: () => void } {
  const staged: OrderTicketPrefill[] = [];
  const onEvent = (e: Event) => staged.push((e as CustomEvent<OrderTicketPrefill>).detail);
  window.addEventListener(ORDER_TICKET_PREFILL_EVENT, onEvent);
  return { staged, stop: () => window.removeEventListener(ORDER_TICKET_PREFILL_EVENT, onEvent) };
}

function withProposal(over: Partial<SetupProposal>): Board {
  return { ...WITH_PROPOSAL, proposals: WITH_PROPOSAL.proposals.map(p => ({ ...p, ...over })) };
}

beforeEach(() => {
  _resetConfirmedDeskVenueStoreForTests();
  // This fixture represents the backend-confirmed Paper desk, not a cached
  // Gateway mode. Stage refuses an unknown venue before opening a ticket.
  confirmDeskVenue('paper');
  _resetSleeveForTests();
  _resetDismissedForTests();
  sessionStorage.clear();
  // Every read here is the fake desk's: the Paper sleeve risks $20 a trade.
  vi.stubGlobal('fetch', vi.fn(async (input: unknown) => {
    if (/\/api\/ibkr\/status$/.test(String(input))) {
      return new Response(JSON.stringify({ venue: 'paper', mode: 'paper', connected: true }), { status: 200 });
    }
    if (/\/api\/bot\/session$/.test(String(input))) {
      return new Response(JSON.stringify({ caps: { venue: 'paper', risk_usd: 20, working_ttl_sec: 3 },
        caps_bounds: { risk_usd: [1, 10_000] } }), { status: 200 });
    }
    return new Response('{}', { status: 404 });
  }));
});

afterEach(() => {
  cleanup();
  _resetConfirmedDeskVenueStoreForTests();
  openStockView.mockReset();
  resetSetupsBoardFilterForTests();
  localStorage.clear();
  vi.unstubAllGlobals();
});

/** The first cell of every body row: the symbol on the board, the group on the scoreboard. */
const firstCells = () => screen.getAllByRole('row').slice(1).map(r => r.querySelector('td, th')?.textContent);

describe('SetupsBoard', () => {
  it('shows state, levels, the tape read and a stage button only on a proposal', () => {
    const onOpen = vi.fn();
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={onOpen} risk={RISK} />,
    );
    expect(screen.getByText('Near')).toBeTruthy();
    expect(screen.getByText('Leg up +7.2%')).toBeTruthy();
    expect(screen.getByText('GO')).toBeTruthy();
    expect(screen.getByText('BLIND')).toBeTruthy();
    expect(screen.getByText('2¢')).toBeTruthy();
    expect(screen.getByText('Target first')).toBeTruthy();
    // Every setup in its own words (ADR 031).
    expect(screen.getByText('Flag · 2 bars')).toBeTruthy();
    expect(screen.getByText('Red −3.2%')).toBeTruthy();
    expect(screen.getAllByText('Bull flag')).toHaveLength(1);
    expect(screen.getAllByText('Stage ticket')).toHaveLength(1);
    fireEvent.click(screen.getByText('Open L2'));
    expect(onOpen).toHaveBeenCalledWith('QMBL');
  });

  it('stages a BUY limit at the entry, sized by the risk per trade, and places nothing', () => {
    const { staged, stop } = captureStaged();
    const onOpen = vi.fn();
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={onOpen} risk={RISK} />,
    );
    const stage = screen.getByText('Stage ticket');
    expect(stage.getAttribute('data-tip')).toMatch(/for 250 shares: \$20 of risk \(the Paper sleeve's risk per trade\) over 8¢ a share/);
    fireEvent.click(stage);
    stop();
    expect(onOpen).toHaveBeenCalledWith('NVXA');
    // $20 over the 0.08 risk a share: 250 shares, never Settings > Trade's default quantity.
    expect(staged[0]).toMatchObject({ symbol: 'NVXA', side: 'BUY', orderType: 'LMT', limitPrice: '4.38', quantityValue: '250' });
  });

  it('locks Stage with the reason when the bot takes the proposal or it is not a trade', () => {
    const rows = SAMPLE_SETUPS_BOARD.rows.map(r => (r.proposal ? { ...r, proposal: { ...r.proposal, taken_by: 'bot' as const } } : r));
    render(<SetupsBoard rows={rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} risk={RISK} />);
    const stage = screen.getByText('Stage ticket') as HTMLButtonElement;
    expect(stage.disabled).toBe(true);
    expect(stage.getAttribute('data-why')).toBe('The bot is taking this trade: a buy of your own would double it.');
  });

  it('shows a setup the template filtered out, with the rule', () => {
    const row = { ...SAMPLE_SETUPS_BOARD.rows[0], state: 'filtered' as const, proposal: null,
      reason: 'filtered: float 30.0M over 10.0M' };
    render(<SetupsBoard rows={[row]} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} risk={RISK} />);
    expect(screen.getByText('Filtered')).toBeTruthy();
  });

  it('says what it watches when there is nothing to show', () => {
    render(<SetupsBoard rows={[]} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} risk={RISK} />);
    expect(screen.getByText(/No setups right now/)).toBeTruthy();
  });

  it('explains every chip on hover, never with the row\'s own title on top', () => {
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} risk={RISK} />,
    );
    const near = screen.getByText('Near');
    expect(near.getAttribute('data-tip-title')).toBe('Near · First pullback');
    expect(near.getAttribute('data-tip')).toMatch(/Price is a few cents under the trigger/);
    expect(screen.getByText('BLIND').getAttribute('data-tip')).toMatch(/^BLIND: Nova holds no Level 2 line/);
    const flag = screen.getByText('Flag · 2 bars');
    expect(flag.getAttribute('data-tip')).toMatch(/The flag is in/);
    expect(flag.getAttribute('data-tip')).toMatch(/Pole: 3 green candles, \+7\.9% to 5\.62/);
    expect(near.closest('tr')?.getAttribute('title')).toBeNull();
  });

  it('sorts by a header: prices highest first, To go nearest first, then back to the board order', () => {
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} risk={RISK} />,
    );
    const board = ['NVXA', 'QMBL', 'HLTR', 'ORBT', 'KSTR', 'PLNX'];
    expect(firstCells()).toEqual(board);
    fireEvent.click(screen.getByRole('columnheader', { name: 'Trigger' }));
    // No setup yet (ORBT, PLNX) has no trigger: last, in the board's order.
    expect(firstCells()).toEqual(['QMBL', 'KSTR', 'NVXA', 'HLTR', 'ORBT', 'PLNX']);
    const toGo = screen.getByRole('columnheader', { name: 'To go' });
    fireEvent.click(toGo);
    // A triggered row shows how it went, not a distance: it sorts with the unknowns.
    expect(firstCells()).toEqual(['NVXA', 'KSTR', 'QMBL', 'HLTR', 'ORBT', 'PLNX']);
    expect(toGo.getAttribute('aria-sort')).toBe('ascending');
    fireEvent.click(toGo);
    fireEvent.click(toGo);
    expect(firstCells()).toEqual(board);
  });
});

describe('SetupsScoreboard', () => {
  it('splits the scores by the tape at the trigger', () => {
    render(<SetupsScoreboard data={SAMPLE_SETUPS_SCOREBOARD} error={null} loading={false} days={5} onDays={vi.fn()} />);
    expect(screen.getByText('All armed setups')).toBeTruthy();
    expect(screen.getByText('Tape at the trigger')).toBeTruthy();
    expect(screen.getByText('Tape said go')).toBeTruthy();
    expect(screen.getByText('14 armed since 2026-09-18')).toBeTruthy();
    const labels = screen.getAllByRole('rowheader').map(th => th.textContent);
    expect(labels.slice(0, 5)).toEqual(['All armed setups', 'Tape said go', 'Tape said wait', 'No Level 2 line', 'Never triggered']);
  });

  it('sorts the groups inside each split, and keeps the splits and the all-setups row in place', () => {
    render(<SetupsScoreboard data={SAMPLE_SETUPS_SCOREBOARD} error={null} loading={false} days={5} onDays={vi.fn()} />);
    fireEvent.click(screen.getByRole('columnheader', { name: 'Net R' }));
    expect(firstCells().slice(0, 9)).toEqual([
      'All armed setups',
      'Tape at the trigger', 'Tape said go', 'No Level 2 line', 'Tape said wait', 'Never triggered',
      'Grade when armed', 'Grade A', 'Grade B',
    ]);
    fireEvent.click(screen.getByRole('columnheader', { name: 'Net R' }));
    // Lowest first; a group with no scored setup (never triggered) stays last.
    expect(firstCells().slice(1, 6)).toEqual([
      'Tape at the trigger', 'Tape said wait', 'No Level 2 line', 'Tape said go', 'Never triggered',
    ]);
  });

  it('states an error instead of an empty table', () => {
    render(
      <SetupsScoreboard data={null} error="Scoreboard unavailable: HTTP 503" loading={false} days={5} onDays={vi.fn()} />,
    );
    expect(screen.getByText('Scoreboard unavailable: HTTP 503')).toBeTruthy();
  });
});

describe('SetupsAlertCard', () => {
  it("names the setup, stages on request sized by the sleeve's risk, and then steps aside", async () => {
    const { staged, stop } = captureStaged();
    render(<SetupsAlertCard board={WITH_PROPOSAL} />);
    const card = screen.getByRole('status');
    expect(card.textContent).toContain('NVXA');
    expect(card.textContent).toContain('4.37');
    const stage = screen.getByTestId('setups-alert-stage');
    await waitFor(() => expect(stage.getAttribute('data-tip')).toMatch(/the Paper sleeve's risk per trade/));
    expect(stage.textContent).toBe('Stage ticket · 250');
    fireEvent.click(stage);
    stop();
    expect(openStockView).toHaveBeenCalledWith('NVXA');
    expect(staged[0]).toMatchObject({ symbol: 'NVXA', limitPrice: '4.38', quantityValue: '250' });
    expect(screen.queryByRole('status')).toBeNull();
    expect(isDismissed('sample-1')).toBe(true);
  });

  it('says the bot is taking it, with nothing to do, and locks Stage', () => {
    render(<SetupsAlertCard board={withProposal({ taken_by: 'bot' })} />);
    expect(screen.getByTestId('setups-alert-verdict').textContent).toBe('The bot is taking this — nothing to do.');
    const stage = screen.getByTestId('setups-alert-stage') as HTMLButtonElement;
    expect(stage.disabled).toBe(true);
    expect(stage.getAttribute('data-why')).toBe('The bot is taking this trade: a buy of your own would double it.');
    expect(stage.textContent).toBe('Stage ticket');
  });

  it('says Auto-entry is taking it', () => {
    render(<SetupsAlertCard board={withProposal({ taken_by: 'auto_entry' })} />);
    expect(screen.getByTestId('setups-alert-verdict').textContent).toBe('Auto-entry is taking this — nothing to do.');
    expect(screen.getByTestId('setups-alert-stage').getAttribute('data-why')).toMatch(/Auto-entry is buying this/);
  });

  it('says a proposal is not a trade, with its reasons, and locks Stage with them', () => {
    render(<SetupsAlertCard board={withProposal({ not_a_trade: { reasons: ['grade C: 2 of 5 pillars'] },
      pillars: { passed: 2, known: 5, total: 5 }, grade: 'C' })} />);
    expect(screen.getByTestId('setups-alert-verdict').textContent).toBe('Not a trade: grade C: 2 of 5 pillars. '
      + 'Nova does not buy it either: not the bot, not Auto-entry, not Approve.');
    expect(screen.getByRole('status').textContent).toContain('grade C 2/5');
    expect(screen.getByTestId('setups-alert-stage').getAttribute('data-why')).toBe('Not a trade: grade C: 2 of 5 pillars.');
  });

  it('shares one dismissed list with the Bots inbox, kept for the session', () => {
    render(<SetupsAlertCard board={WITH_PROPOSAL} />);
    fireEvent.click(screen.getByTestId('setups-alert-dismiss'));
    expect(screen.queryByRole('status')).toBeNull();
    expect(JSON.parse(sessionStorage.getItem(PROPOSAL_DISMISSED_KEY) ?? '{}')).toEqual({ schema_version: 1, ids: ['sample-1'] });
    cleanup();
    // The inbox (or any reader) dismissing it elsewhere keeps the card away too.
    _resetDismissedForTests();
    sessionStorage.clear();
    render(<SetupsAlertCard board={WITH_PROPOSAL} />);
    expect(screen.getByRole('status')).toBeTruthy();
    act(() => dismiss(['sample-1']));
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows the tape as it reads now, not as it read when raised', () => {
    const turned: Board = { ...WITH_PROPOSAL, proposals: WITH_PROPOSAL.proposals.map(p => ({ ...p, tape_now: 'veto' })) };
    render(<SetupsAlertCard board={turned} />);
    const card = screen.getByRole('status');
    expect(card.textContent).toContain('Tape: no');
    expect(card.textContent).toContain('it said go when this was raised');
  });

  it('shows nothing without an open proposal', () => {
    render(<SetupsAlertCard board={SAMPLE_SETUPS_BOARD} />);
    expect(screen.queryByRole('status')).toBeNull();
  });
});

describe('the dismissed list', () => {
  it('reads only its own version, and ignores anything else', () => {
    expect(parseDismissed(JSON.stringify({ schema_version: 1, ids: ['a', 7, 'b'] }))).toEqual(['a', 'b']);
    expect(parseDismissed(JSON.stringify({ schema_version: 2, ids: ['a'] }))).toEqual([]);
    expect(parseDismissed(JSON.stringify(['a']))).toEqual([]);
    expect(parseDismissed(null)).toEqual([]);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(parseDismissed('{not json')).toEqual([]);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('SetupsPanel', () => {
  afterEach(() => { stream.value = null; });

  it('filters the board by setup, with a count on each chip, and names the setup\'s template in play', () => {
    const setups = SAMPLE_SETUPS_BOARD.setups!.map(s => (s.id === 'first_pullback' ? { ...s, templates_watched: 3 } : s));
    stream.value = { connected: true, board: { ...SAMPLE_SETUPS_BOARD, source: 'live', setups } };
    render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    // What each level does, said plainly: at Strategy the bot does place (ADR 042 draft).
    const about = screen.getByTestId('setups-description').textContent ?? '';
    expect(about).toMatch(/Eyes proposes when a setup is near its trigger/);
    expect(about).toMatch(/Strategy also lets Nova buy its go triggers on Paper and Sim while the bot is Active/);
    expect(about).not.toMatch(/never places/);
    expect(screen.getByTestId('setups-filter-all').textContent).toBe('All 6');
    expect(screen.getByTestId('setups-filter-first_pullback').textContent).toBe('First pullback 4');
    expect(screen.getByTestId('setups-filter-bull_flag').textContent).toBe('Bull flag 1');
    expect(screen.getByText(/proposing: first pullback, bull flag/)).toBeTruthy();
    // No scanner yet: the chip is locked and says why.
    const micro = screen.getByTestId('setups-filter-micro_pullback') as HTMLButtonElement;
    expect(micro.disabled).toBe(true);
    expect(micro.getAttribute('data-why')).toMatch(/one-second bars/);
    fireEvent.click(screen.getByTestId('setups-filter-bull_flag'));
    expect(screen.queryByText('NVXA')).toBeNull();
    expect(screen.getByText('KSTR')).toBeTruthy();
    fireEvent.click(screen.getByTestId('setups-filter-first_pullback'));
    expect(screen.getByText(/First pullback template Default \(pre-registered\) \(\+2 scored alongside\)/)).toBeTruthy();
  });

  it('says when the board is the Sim eyes over a recording, or why it cannot be', () => {
    const replay = { kind: 'capture', date: '2026-09-23', symbol: 'WHLR', playhead: 1, at: 1, loading: false,
      error: null, note: null };
    stream.value = { connected: true, board: { ...SAMPLE_SETUPS_BOARD, source: 'sim', replay } };
    const { unmount } = render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText(/Sim eyes on WHLR 2026-09-23 · following the playhead/)).toBeTruthy();
    unmount();
    // Anything else off the edge: what Nova's live eyes recorded at the playhead, or a stated absence.
    const at = Date.UTC(2026, 8, 24, 12, 7, 2) / 1000;        // 08:07:02 ET
    stream.value = { connected: true, board: { ...SAMPLE_SETUPS_BOARD, source: 'sim', rows: [],
      replay: { ...replay, kind: 'journal', symbol: null, date: '2026-09-24', at,
        note: 'Nova\'s eyes\' record for 2026-09-24 starts at 07:27:22 ET.' } } };
    render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    const status = screen.getByTestId('setups-status');
    expect(status.textContent).toBe(
      'Recorded · what Nova\'s eyes saw live at 08:07:02 ET on 2026-09-24 · Nova\'s eyes\' record for 2026-09-24 starts at 07:27:22 ET.');
    expect(status.getAttribute('data-tip')).toMatch(/what Nova's live eyes recorded at the playhead/);
    expect(screen.getByText('Nothing forming at 08:07:02 ET.')).toBeTruthy();
  });

  it('explains itself outside the main desk window', () => {
    render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText(/runs in the main desk window/)).toBeTruthy();
  });
});
