/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { TRADE_DEFAULTS_WAITING } from '../constantGroups/trade_defaults';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { BotProposalsInbox } from './BotProposalsInbox';
import type { SetupsBoard } from '../setups/types';

const fixture = vi.hoisted(() => ({
  venue: 'paper' as DeskVenue | null,
  staged: vi.fn(() => true),
  dismissed: vi.fn(),
  ids: new Set<string>(),
}));
vi.mock('../ibkr/confirmedDeskVenue', () => ({
  useConfirmedDeskVenue: () => fixture.venue,
  getConfirmedDeskVenueSnapshot: () => ({ venue: fixture.venue, generation: fixture.venue ? 'confirmed-test' : null }),
  subscribeConfirmedDeskVenue: () => () => {},
  isConfirmedDeskVenueSnapshotCurrent: () => true,
}));
vi.mock('../setups', async (importOriginal) => ({
  ...await importOriginal<Record<string, unknown>>(),
  useSetupsBoard: () => ({ board: {
    rows: [], proposals: [{ id: 'p1', status: 'open', symbol: 'AAPL', kind: 'bull_flag', created_at: 100,
      trigger: 10, entry: 10, stop: 9.9, risk: 0.1, target1: 10.2, tape_now: 'go' }],
  } as unknown as SetupsBoard }),
  useSleeveRisk: () => ({ riskUsd: 20, source: 'sleeve', venue: 'paper', why: null }),
  dismissedProposals: () => fixture.ids,
  subscribeDismissedProposals: () => () => {},
  dismissProposals: (...args: unknown[]) => fixture.dismissed(...args),
  stageSetupTicket: (...args: unknown[]) => fixture.staged(...args),
}));

describe('proposal inbox Stage uses the confirmed desk venue', () => {
  beforeEach(() => {
    fixture.venue = 'paper'; fixture.staged.mockReset().mockReturnValue(true); fixture.dismissed.mockReset();
  });
  afterEach(() => { cleanup(); history.replaceState(null, '', '/'); });
  const show = () => render(<BotProposalsInbox proposals={[]} audit={[]} resolve={vi.fn()} openTrader={vi.fn()} />);

  it('disables an unknown-venue Stage visibly and leaves its proposal available', () => {
    fixture.venue = null;
    show();
    const stage = screen.getByTestId('bots-stage-AAPL') as HTMLButtonElement;
    expect(stage.disabled).toBe(true);
    expect(stage.dataset.why).toBe(TRADE_DEFAULTS_WAITING);
    fireEvent.click(stage);
    expect(fixture.staged).not.toHaveBeenCalled();
    expect(fixture.dismissed).not.toHaveBeenCalled();
    expect(screen.getByTestId('bots-setup-proposal-AAPL')).toBeTruthy();
  });

  it('stages and dismisses a ready Paper proposal', () => {
    show();
    const stage = screen.getByTestId('bots-stage-AAPL') as HTMLButtonElement;
    expect(stage.disabled).toBe(false);
    fireEvent.click(stage);
    expect(fixture.staged).toHaveBeenCalledWith('AAPL', '10.00', expect.any(Function), 200);
    expect(fixture.dismissed).toHaveBeenCalledWith(['p1']);
  });

  it('keeps a proposal when a previously ready Stage is refused', () => {
    fixture.staged.mockReturnValue(false);
    show();
    fireEvent.click(screen.getByTestId('bots-stage-AAPL'));
    expect(fixture.dismissed).not.toHaveBeenCalled();
  });

  it('explains the sample refusal rather than waiting for a real backend', () => {
    fixture.venue = null;
    history.replaceState(null, '', '/?view=sample');
    show();
    expect((screen.getByTestId('bots-stage-AAPL') as HTMLButtonElement).dataset.why).toBe(SAMPLE_WRITE_REFUSAL);
  });
});
