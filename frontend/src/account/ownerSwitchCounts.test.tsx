/**
 * @vitest-environment jsdom
 *
 * The switch (ADR 072, mockup three-books v1 item 1): five picks -- All, You, Claude, The brain, Earlier bots --
 * Earlier bots opening a menu of the retired bots that traded. On Reports each pick counts its closed trades and a
 * bot the journal counts joins the menu (mockup reports-v1 item 1). Live reads You only, greyed, with its reason.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OWNER_LIVE_WHY } from '../constantGroups/owners';
import { OwnerSwitch } from './OwnerSwitch';
import { ALL_VIEW } from './ownerView';

afterEach(cleanup);

const labels = () => screen.getAllByRole('button').map((b) => b.textContent);

describe('OwnerSwitch', () => {
  it('draws five picks and opens on All', () => {
    render(<OwnerSwitch view={ALL_VIEW} onView={vi.fn()} bots={['live_trader']} live={false} />);
    expect(labels()).toEqual(['All', 'You', 'Claude', 'The brain', 'Earlier bots▾']);
    expect(screen.getByTestId('account-owner-all').getAttribute('aria-pressed')).toBe('true');
  });

  it('picks a trader directly; Earlier bots opens its menu of the retired bots that traded', () => {
    const onView = vi.fn();
    render(<OwnerSwitch view={ALL_VIEW} onView={onView} bots={['live_trader']} live={false} />);
    fireEvent.click(screen.getByTestId('account-owner-brain'));
    expect(onView).toHaveBeenLastCalledWith({ book: 'brain', bot: null });
    fireEvent.click(screen.getByTestId('account-owner-earlier_bots'));
    expect(onView).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('account-owner-menu').textContent).toBe('All earlier botsLive Trader');
    expect(screen.queryByTestId('account-owner-bot-claude')).toBeNull();   // Claude left the bots' menu
    fireEvent.click(screen.getByTestId('account-owner-bot-live_trader'));
    expect(onView).toHaveBeenLastCalledWith({ book: 'earlier_bots', bot: 'live_trader' });
  });

  it("names the picked bot on its pick", () => {
    render(<OwnerSwitch view={{ book: 'earlier_bots', bot: 'live_trader' }} onView={vi.fn()} bots={['live_trader']} live={false} />);
    expect(screen.getByTestId('account-owner-earlier_bots').textContent).toBe('Live Trader▾');
  });

  it('counts the trades behind each pick on Reports', () => {
    render(<OwnerSwitch view={ALL_VIEW} onView={vi.fn()} bots={[]} live={false}
      counts={{ all: 273, byBot: { live_trader: 273 }, books: { you: 127, claude: 17, brain: 0, earlier_bots: 273 } }} />);
    expect(labels()).toEqual(['All', 'You127', 'Claude17', 'The brain0', 'Earlier bots273▾']);
    fireEvent.click(screen.getByTestId('account-owner-earlier_bots'));
    expect(screen.getByTestId('account-owner-bot-all').textContent).toContain('273 trades');
    expect(screen.getByTestId('account-owner-bot-live_trader').textContent).toContain('273 trades');
  });

  it('keeps the Overview menu without counts', () => {
    render(<OwnerSwitch view={ALL_VIEW} onView={vi.fn()} bots={['live_trader']} live={false} />);
    fireEvent.click(screen.getByTestId('account-owner-earlier_bots'));
    expect(screen.getByTestId('account-owner-bot-all').textContent).not.toContain('trades');
  });

  it('on Live shows You only, greyed, with its reason', () => {
    render(<OwnerSwitch view={ALL_VIEW} onView={vi.fn()} bots={['live_trader']} live />);
    expect(labels()).toEqual(['You']);
    const you = screen.getByTestId('account-owner-you') as HTMLButtonElement;
    expect([you.disabled, you.title]).toEqual([true, OWNER_LIVE_WHY]);
  });
});
