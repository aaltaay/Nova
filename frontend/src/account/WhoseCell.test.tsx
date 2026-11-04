/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ownerBotsHoldSentence,
  ownerCloseBotsConfirm,
  ownerCloseBotsTitle,
} from '../constantGroups/owners';
import { CloseBotsButton, WhoseChip } from './WhoseCell';

const closeBots = vi.hoisted(() => vi.fn(async () => undefined));
vi.mock('./ownersApi', () => ({ closeBots }));

afterEach(() => {
  cleanup();
  closeBots.mockReset();
});

describe('the words of a Close on a bots\' row (ADR 069 decision 4)', () => {
  it('buys a short back and sells a long', () => {
    expect(ownerCloseBotsConfirm(-19)).toBe('Buy back all 19?');
    expect(ownerCloseBotsConfirm(1200)).toBe('Sell all 1,200?');
    expect(ownerCloseBotsTitle('ORCL', -19)).toBe("Buy back every bot's ORCL short -- 19 shares in all -- at market. Your shares stay.");
    expect(ownerCloseBotsTitle('ORCL', 19)).toBe("Sell every bot's ORCL -- 19 shares in all -- at market. Your shares stay.");
  });

  it('says where the shares are after a refusal', () => {
    expect(ownerBotsHoldSentence(-19)).toBe(" The 19 short is the bots' -- Close on their row buys it back.");
    expect(ownerBotsHoldSentence(40)).toBe(" The 40 shares are the bots' -- Close on their row sells them.");
  });
});

describe('WhoseChip', () => {
  it("names you, or the bot; the pill is the desk's look", () => {
    render(<><WhoseChip owner="you" bot={null} /><WhoseChip owner="bots" bot="live_trader" pill /></>);
    const [you, bot] = screen.getAllByTestId('account-whose');
    expect([you.textContent, you.className]).toEqual(['You', 'acct-who is-you']);
    expect([bot.textContent, bot.className]).toEqual(['Live Trader', 'acct-who is-bots is-pill']);
  });

  it("still names Auto-entry on your row: the shares are yours to sell, the buy was its", () => {
    render(<WhoseChip owner="you" bot="auto_entry" />);
    expect(screen.getByTestId('account-whose').textContent).toBe('Auto-entry');
  });
});

describe('CloseBotsButton', () => {
  it('draws the word on the desk and the X on the Account page', () => {
    render(<><CloseBotsButton symbol="ORCL" qty={-19} paper look="word" /><CloseBotsButton symbol="INTC" qty={5} paper /></>);
    expect(screen.getByTestId('account-close-bots-ORCL').textContent).toBe('Close');
    expect(screen.getByTestId('account-close-bots-INTC').textContent).toBe('');
  });

  it("says a refused Close's reason on the row", async () => {
    closeBots.mockRejectedValueOnce(new Error('The bots hold no ORCL'));
    render(<CloseBotsButton symbol="ORCL" qty={-19} paper look="word" />);
    const close = screen.getByTestId('account-close-bots-ORCL');
    fireEvent.click(close);
    await act(async () => { fireEvent.click(close); });
    expect(screen.getByTestId('account-close-bots-error').textContent).toContain('The bots hold no ORCL');
  });

  it('keeps a click off the row around it', () => {
    const row = vi.fn();
    render(<div onClick={row}><CloseBotsButton symbol="ORCL" qty={-19} paper look="word" /></div>);
    fireEvent.click(screen.getByTestId('account-close-bots-ORCL'));
    expect(row).not.toHaveBeenCalled();
  });
});
