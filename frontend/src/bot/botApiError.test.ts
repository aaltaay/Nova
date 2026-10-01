import { describe, expect, it } from 'vitest';
import {
  BOT_ERROR_ARM_REQUIRED,
  BOT_ERROR_NEED_API_KEY,
  BOT_ERROR_NOT_ACTIVE,
} from '../constantGroups/bot';
import { messageFromBotApiBody } from './botApiError';

describe('messageFromBotApiBody', () => {
  it('turns a string 401 detail into a visible API key message', () => {
    expect(messageFromBotApiBody(401, { detail: 'Invalid or missing X-Nova-Api-Key' }))
      .toBe(BOT_ERROR_NEED_API_KEY);
  });

  it('turns BOT_ARM_REQUIRED into Activate-then-Strategy copy', () => {
    expect(messageFromBotApiBody(403, {
      detail: { error: 'desk arm token required', reason: 'BOT_ARM_REQUIRED' },
    })).toBe(BOT_ERROR_ARM_REQUIRED);
  });

  it('turns BOT_NOT_ACTIVE into Activate copy', () => {
    expect(messageFromBotApiBody(409, {
      detail: { error: 'desk is Not active -- Activate before live fire', reason: 'BOT_NOT_ACTIVE' },
    })).toBe(BOT_ERROR_NOT_ACTIVE);
  });

  it('keeps other refusals in their own words, without the code', () => {
    expect(messageFromBotApiBody(409, {
      detail: { error: 'bot is Level 0 -- fully dark', reason: 'BOT_L0_DARK' },
    })).toBe('bot is Level 0 -- fully dark');
    // ADR 042: the Activate refusals and the stock-mode rules answer the same shape.
    expect(messageFromBotApiBody(409, {
      detail: { reason: 'BOT_TRIP_LATCHED', error: 'The bot trip fired at 09:42 ET (P&L -$52.10). Activate with re-enable to trade again today.' },
    })).toBe('The bot trip fired at 09:42 ET (P&L -$52.10). Activate with re-enable to trade again today.');
    expect(messageFromBotApiBody(409, {
      detail: { reason: 'STOCK_MODE_LIVE', error: 'Nova places for a stock only on Paper and Sim', field: 'buy' },
    })).toBe('Nova places for a stock only on Paper and Sim');
    // A reason that is a sentence, not a code, is kept beside the error.
    expect(messageFromBotApiBody(409, { detail: { error: 'refused', reason: 'the padlock is locked' } }))
      .toBe('refused -- the padlock is locked');
  });
});
