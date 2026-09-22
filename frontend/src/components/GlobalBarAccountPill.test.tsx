/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AccountPillButton, AccountPillMenu } from './GlobalBarAccountPill';
import type { HeaderAccountPillView } from './headerAccountPill';

afterEach(cleanup);

const view: HeaderAccountPillView = {
  kind: 'live',
  label: 'Individual Margin (U1234567)',
  structure: 'Individual',
  accountClass: 'margin',
  id: 'U1234567',
  tooltip: 'IBKR account U1234567 (LIVE). Login username never exposed.',
  accounts: [
    { id: 'U1234567', active: true },
    { id: 'U7654321', active: false },
  ],
  note: 'Switching accounts happens in IB Gateway.',
};

describe('AccountPillButton', () => {
  it('shows the full label, never truncated, with the kind and id on the element', () => {
    const onToggle = vi.fn();
    const onHover = vi.fn();
    render(<AccountPillButton view={view} open={false} menuId="m" onToggle={onToggle} onHover={onHover} />);
    const pill = screen.getByTestId('global-bar-account-pill');
    expect(pill.textContent).toContain('Individual Margin (U1234567)');
    expect(pill.dataset.kind).toBe('live');
    expect(pill.dataset.accountId).toBe('U1234567');
    expect(pill.title).toBe(view.tooltip);
    expect(pill.getAttribute('aria-label')).toBe('Trading account: Individual Margin (U1234567)');
    expect(pill.getAttribute('aria-expanded')).toBe('false');
    expect(pill.getAttribute('aria-controls')).toBe('m');
    pill.click();
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('marks a practice account visibly', () => {
    render(
      <AccountPillButton
        view={{ ...view, kind: 'practice', label: 'Nova Paper Margin (NOVA-PAPER)', id: 'NOVA-PAPER' }}
        open
        menuId="m"
        onToggle={() => {}}
        onHover={() => {}}
      />,
    );
    const pill = screen.getByTestId('global-bar-account-pill');
    expect(pill.className).toContain('global-app-bar__account-pill--practice');
    expect(pill.getAttribute('aria-expanded')).toBe('true');
  });
});

describe('AccountPillMenu', () => {
  it('lists every managed account, marks the active one, and says why it is information only', () => {
    render(<AccountPillMenu view={view} />);
    const items = screen.getAllByTestId('global-bar-account-pill-item');
    expect(items.map((el) => el.dataset.accountId)).toEqual(['U1234567', 'U7654321']);
    expect(items[0].getAttribute('aria-current')).toBe('true');
    expect(items[0].textContent).toContain('active');
    expect(items[1].getAttribute('aria-current')).toBeNull();
    expect(items[1].textContent).not.toContain('active');
    const menu = screen.getByTestId('global-bar-account-pill-menu');
    expect(menu.textContent).toContain(view.tooltip);
    expect(menu.textContent).toContain(view.note);
  });
});
