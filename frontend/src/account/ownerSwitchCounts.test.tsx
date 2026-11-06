/**
 * @vitest-environment jsdom
 *
 * The switch on Reports (ADR 069 decision 6, mockup reports-v1 item 1): the Bots menu counts each pick's closed
 * trades, and a bot the journal counts joins the list.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OwnerSwitch } from './OwnerSwitch';
import { ALL_VIEW } from './ownerView';

afterEach(cleanup);

describe('OwnerSwitch counts', () => {
  it('counts the trades behind each pick of the Bots menu', () => {
    render(<OwnerSwitch view={ALL_VIEW} onView={vi.fn()} bots={['live_trader']} live={false}
      counts={{ all: 239, byBot: { live_trader: 233, claude: 6 } }} />);
    fireEvent.click(screen.getByTestId('account-owner-bots'));
    expect(screen.getByTestId('account-owner-bot-all').textContent).toContain('239 trades');
    expect(screen.getByTestId('account-owner-bot-live_trader').textContent).toContain('233 trades');
    expect(screen.getByTestId('account-owner-bot-claude').textContent).toContain('6 trades');
  });

  it('keeps the Overview menu as it was', () => {
    render(<OwnerSwitch view={ALL_VIEW} onView={vi.fn()} bots={['live_trader']} live={false} />);
    fireEvent.click(screen.getByTestId('account-owner-bots'));
    expect(screen.getByTestId('account-owner-bot-all').textContent).not.toContain('trades');
    expect(screen.queryByTestId('account-owner-bot-claude')).toBeNull();
  });
});
