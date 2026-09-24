/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ORDER_TICKET_PREFILL_EVENT, type OrderTicketPrefill } from '../ibkr/orderTicketPrefill';
import { SAMPLE_SETUPS_BOARD, SAMPLE_SETUPS_SCOREBOARD } from '../sample_data/sampleSetups';
import { SetupsAlertCard } from './SetupsAlertCard';
import { SetupsBoard } from './SetupsBoard';
import { SetupsPanel } from './SetupsPanel';
import { SetupsScoreboard } from './SetupsScoreboard';
import { resetSetupsBoardFilterForTests } from './setupsBoardFilter';
import type { SetupsBoard as Board } from './types';

const openStockView = vi.fn();
vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => ({ openStockView }) }));
const stream = vi.hoisted(() => ({ value: null as null | { board: unknown; connected: boolean } }));
vi.mock('./SetupsStreamContext', () => ({ useSetupsBoard: () => stream.value }));

const WITH_PROPOSAL: Board = {
  ...SAMPLE_SETUPS_BOARD,
  proposals: SAMPLE_SETUPS_BOARD.rows.flatMap(r => (r.proposal ? [r.proposal] : [])),
};

function captureStaged(): { staged: OrderTicketPrefill[]; stop: () => void } {
  const staged: OrderTicketPrefill[] = [];
  const onEvent = (e: Event) => staged.push((e as CustomEvent<OrderTicketPrefill>).detail);
  window.addEventListener(ORDER_TICKET_PREFILL_EVENT, onEvent);
  return { staged, stop: () => window.removeEventListener(ORDER_TICKET_PREFILL_EVENT, onEvent) };
}

afterEach(() => {
  cleanup();
  openStockView.mockReset();
  resetSetupsBoardFilterForTests();
});

describe('SetupsBoard', () => {
  it('shows state, levels, the tape read and a stage button only on a proposal', () => {
    const onOpen = vi.fn();
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={onOpen} />,
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

  it('stages a BUY limit at the entry and places nothing', () => {
    const { staged, stop } = captureStaged();
    const onOpen = vi.fn();
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={onOpen} />,
    );
    fireEvent.click(screen.getByText('Stage ticket'));
    stop();
    expect(onOpen).toHaveBeenCalledWith('NVXA');
    expect(staged[0]).toMatchObject({ symbol: 'NVXA', side: 'BUY', orderType: 'LMT', limitPrice: '4.38' });
  });

  it('shows a setup the template filtered out, with the rule', () => {
    const row = { ...SAMPLE_SETUPS_BOARD.rows[0], state: 'filtered' as const, proposal: null,
      reason: 'filtered: float 30.0M over 10.0M' };
    render(<SetupsBoard rows={[row]} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText('Filtered')).toBeTruthy();
  });

  it('says what it watches when there is nothing to show', () => {
    render(<SetupsBoard rows={[]} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText(/No setups right now/)).toBeTruthy();
  });

  it('explains every chip on hover, never with the row\'s own title on top', () => {
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />,
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

  it('states an error instead of an empty table', () => {
    render(
      <SetupsScoreboard data={null} error="Scoreboard unavailable: HTTP 503" loading={false} days={5} onDays={vi.fn()} />,
    );
    expect(screen.getByText('Scoreboard unavailable: HTTP 503')).toBeTruthy();
  });
});

describe('SetupsAlertCard', () => {
  it('names the setup, stages on request and then steps aside', () => {
    const { staged, stop } = captureStaged();
    render(<SetupsAlertCard board={WITH_PROPOSAL} />);
    const card = screen.getByRole('status');
    expect(card.textContent).toContain('NVXA');
    expect(card.textContent).toContain('4.37');
    fireEvent.click(screen.getByText('Stage ticket'));
    stop();
    expect(openStockView).toHaveBeenCalledWith('NVXA');
    expect(staged[0]).toMatchObject({ symbol: 'NVXA', limitPrice: '4.38' });
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

describe('SetupsPanel', () => {
  afterEach(() => { stream.value = null; });

  it('filters the board by setup, with a count on each chip, and names the setup\'s template in play', () => {
    const setups = SAMPLE_SETUPS_BOARD.setups!.map(s => (s.id === 'first_pullback' ? { ...s, templates_watched: 3 } : s));
    stream.value = { connected: true, board: { ...SAMPLE_SETUPS_BOARD, source: 'live', setups } };
    render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByTestId('setups-filter-all').textContent).toBe('All 6');
    expect(screen.getByTestId('setups-filter-first_pullback').textContent).toBe('First pullback 4');
    expect(screen.getByTestId('setups-filter-bull_flag').textContent).toBe('Bull flag 1');
    expect(screen.getByText(/proposing: first pullback, bull flag/)).toBeTruthy();
    // No scanner yet: the chip is locked and says why.
    const gng = screen.getByTestId('setups-filter-gap_and_go') as HTMLButtonElement;
    expect(gng.disabled).toBe(true);
    expect(gng.getAttribute('data-why')).toMatch(/no scanner yet/);
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
