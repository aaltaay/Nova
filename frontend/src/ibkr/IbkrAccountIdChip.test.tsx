/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { IbkrStatus } from './types';
import { IbkrAccountIdChip } from './IbkrAccountIdChip';

const status = vi.hoisted(() => ({ current: {} as Partial<IbkrStatus> }));
vi.mock('./useIbkrStatus', () => ({ useIbkrStatus: () => status.current }));

afterEach(cleanup);

describe('IbkrAccountIdChip', () => {
  it('names the account the desk is logged into, and its kind', () => {
    status.current = { connected: true, broker_account_kind: 'paper', account_id: 'DUQ266899', account_ids: ['DUQ266899'] };
    render(<IbkrAccountIdChip />);
    const chip = screen.getByTestId('global-bar-account-id');
    expect(chip.textContent).toBe('DUQ266899');
    expect(chip.dataset.kind).toBe('paper');
    expect(chip.title).toContain('IBKR account DUQ266899 (paper)');
    expect(chip.title).toContain('login username is never exposed');
  });

  it('lists the other managed accounts on the same login', () => {
    status.current = { connected: true, broker_account_kind: 'live', account_id: 'U1234567', account_ids: ['U1234567', 'U7654321'] };
    render(<IbkrAccountIdChip />);
    expect(screen.getByTestId('global-bar-account-id').title).toContain('Other managed accounts on this login: U7654321');
  });

  it('shows nothing while disconnected -- an old id would be a lie', () => {
    status.current = { connected: false, account_id: 'DUQ266899' };
    render(<IbkrAccountIdChip />);
    expect(screen.queryByTestId('global-bar-account-id')).toBeNull();
    status.current = { connected: true, account_id: null };
    render(<IbkrAccountIdChip />);
    expect(screen.queryByTestId('global-bar-account-id')).toBeNull();
  });
});
