/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PracticeResetAction } from './PracticeResetAction';
import { PAPER_ACCOUNT } from './practiceFixtures';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), confirm: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../ux', () => ({ confirmApp: (...args: unknown[]) => mocks.confirm(...args) }));

beforeEach(() => {
  mocks.fetch.mockReset();
  mocks.confirm.mockReset();
  mocks.confirm.mockResolvedValue(true);
  mocks.fetch.mockImplementation(async () => ({
    ok: true, status: 200, json: async () => ({ ...PAPER_ACCOUNT, cash: 50000, starting_cash: 50000 }),
  }));
});

afterEach(cleanup);

async function click(venue: 'paper' | 'sim') {
  await act(async () => { fireEvent.click(screen.getByTestId(`practice-reset-button-${venue}`)); });
}

describe('PracticeResetAction', () => {
  it('confirms, then POSTs /api/practice/reset with the venue and the starting cash', async () => {
    render(<PracticeResetAction venue="paper" />);
    fireEvent.change(screen.getByTestId('practice-reset-cash-paper'), { target: { value: '50,000' } });
    await click('paper');
    expect(mocks.confirm).toHaveBeenCalledTimes(1);
    const dialog = mocks.confirm.mock.calls[0][0] as { title: string; message: string };
    expect(dialog.title).toMatch(/Paper practice account/);
    expect(dialog.message).toContain('$50,000');
    expect(dialog.message).toMatch(/archives the old ledger/);
    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = mocks.fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/practice/reset');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ venue: 'paper', starting_cash: 50000 });
    expect(screen.getByTestId('practice-reset-notice-paper').textContent).toContain('$50,000.00');
    expect((screen.getByTestId('practice-reset-cash-paper') as HTMLInputElement).value).toBe('');
  });

  it('omits starting_cash when the field is blank and names the Sim scope', async () => {
    render(<PracticeResetAction venue="sim" />);
    await click('sim');
    const dialog = mocks.confirm.mock.calls[0][0] as { message: string };
    expect(dialog.message).toMatch(/loaded replay/);
    expect(dialog.message).not.toMatch(/archives/);
    const [, init] = mocks.fetch.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ venue: 'sim' });
  });

  it('does nothing when the operator cancels', async () => {
    mocks.confirm.mockResolvedValue(false);
    render(<PracticeResetAction venue="paper" />);
    await click('paper');
    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(screen.queryByTestId('practice-reset-notice-paper')).toBeNull();
  });

  it('refuses an invalid starting cash before asking', async () => {
    render(<PracticeResetAction venue="paper" />);
    fireEvent.change(screen.getByTestId('practice-reset-cash-paper'), { target: { value: '12.50' } });
    await click('paper');
    expect(mocks.confirm).not.toHaveBeenCalled();
    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toMatch(/whole-dollar/);
  });

  it('reports a backend refusal verbatim', async () => {
    mocks.fetch.mockImplementation(async () => ({
      ok: false, status: 409, json: async () => ({ detail: 'a fill is in flight' }),
    }));
    render(<PracticeResetAction venue="paper" />);
    await click('paper');
    expect(screen.getByRole('alert').textContent).toContain('Reset failed: a fill is in flight');
  });

  it('locks the form while the reset is in flight and says what it is doing', async () => {
    let answer!: (value: unknown) => void;
    mocks.fetch.mockImplementation(() => new Promise(resolve => { answer = resolve; }));
    render(<PracticeResetAction venue="sim" />);
    const button = screen.getByTestId('practice-reset-button-sim') as HTMLButtonElement;
    const cash = screen.getByTestId('practice-reset-cash-sim') as HTMLInputElement;
    expect(button.hasAttribute('data-why')).toBe(false);
    await click('sim');
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('data-why')).toBe('Resetting the Sim account -- wait for it to finish');
    expect(cash.getAttribute('data-why')).toBe('Resetting the Sim account -- wait for it to finish');
    await act(async () => {
      answer({ ok: true, status: 200, json: async () => ({ ...PAPER_ACCOUNT, cash: 100000 }) });
    });
    expect(button.disabled).toBe(false);
    expect(button.hasAttribute('data-why')).toBe(false);
  });

  it('shows the Paper archive note on the form itself', () => {
    render(<PracticeResetAction venue="paper" />);
    expect(screen.getByTestId('practice-reset-paper').textContent).toMatch(/archives the old ledger/);
  });
});
