/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  BOT_ALLOWLIST_EMPTY,
  BOT_SYMBOL_ALLOWLIST_CAP,
} from '../constantGroups/bot';
import { BotAllowlistEditor } from './BotAllowlistEditor';

afterEach(() => {
  cleanup();
});

describe('BotAllowlistEditor', () => {
  it('add/remove call the same helpers StrategyAllowlistCard uses', () => {
    const add = vi.fn();
    const remove = vi.fn();
    render(
      <BotAllowlistEditor
        testId="bot-arm-allowlist"
        symbols={['ABCD']}
        add={add}
        remove={remove}
      />,
    );

    fireEvent.change(screen.getByTestId('bot-arm-allowlist-input'), {
      target: { value: 'efgh' },
    });
    fireEvent.click(screen.getByTestId('bot-arm-allowlist-add'));
    expect(add).toHaveBeenCalledWith('efgh');

    fireEvent.click(screen.getByTestId('bot-arm-allowlist-remove-ABCD'));
    expect(remove).toHaveBeenCalledWith('ABCD');
  });

  it('shows the Strategy-tab empty state', () => {
    render(
      <BotAllowlistEditor
        testId="bot-strategy-allowlist"
        symbols={[]}
        add={vi.fn()}
        remove={vi.fn()}
      />,
    );
    expect(screen.getByText(BOT_ALLOWLIST_EMPTY)).toBeTruthy();
  });

  it('will not add at BOT_SYMBOL_ALLOWLIST_CAP', () => {
    const add = vi.fn();
    const full = Array.from({ length: BOT_SYMBOL_ALLOWLIST_CAP }, (_, i) => `S${i}`);
    render(
      <BotAllowlistEditor
        testId="bot-arm-allowlist"
        symbols={full}
        add={add}
        remove={vi.fn()}
      />,
    );
    expect((screen.getByTestId('bot-arm-allowlist-add') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId('bot-arm-allowlist-add'));
    expect(add).not.toHaveBeenCalled();
  });
});
