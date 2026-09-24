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
});

describe('SetupsBoard', () => {
  it('shows state, levels, the tape read and a stage button only on a proposal', () => {
    const onOpen = vi.fn();
    render(
      <SetupsBoard rows={SAMPLE_SETUPS_BOARD.rows} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={onOpen} />,
    );
    expect(screen.getByText('Near')).toBeTruthy();
    expect(screen.getByText('Leg up')).toBeTruthy();
    expect(screen.getByText('Tape: go')).toBeTruthy();
    expect(screen.getByText('Tape: blind')).toBeTruthy();
    expect(screen.getByText('2¢ under')).toBeTruthy();
    expect(screen.getByText('Target first')).toBeTruthy();
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

  it('names the template in play on the live board', () => {
    stream.value = { connected: true, board: { ...SAMPLE_SETUPS_BOARD, source: 'live', templates_watched: 3,
      template: { id: 'default', rev: 1, name: 'Default (pre-registered)' } } };
    render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText(/template Default \(pre-registered\) \(\+2 scored alongside\)/)).toBeTruthy();
  });

  it('says when the board is the Sim eyes over a recording, or why it cannot be', () => {
    const replay = { kind: 'capture', date: '2026-09-23', symbol: 'WHLR', playhead: 1, at: 1, loading: false,
      error: null, note: null };
    stream.value = { connected: true, board: { ...SAMPLE_SETUPS_BOARD, source: 'sim', replay,
      template: { id: 'default', rev: 1, name: 'Default (pre-registered)' } } };
    const { unmount } = render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText(/Sim eyes on WHLR 2026-09-23 · following the playhead/)).toBeTruthy();
    unmount();
    stream.value = { connected: true, board: { ...SAMPLE_SETUPS_BOARD, source: 'sim', rows: [],
      replay: { ...replay, kind: 'historical', note: 'no Level 2 in a download' } } };
    render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText(/Sim eyes on WHLR 2026-09-23 · no Level 2 in a download/)).toBeTruthy();
  });

  it('explains itself outside the main desk window', () => {
    render(<SetupsPanel selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByText(/runs in the main desk window/)).toBeTruthy();
  });
});
