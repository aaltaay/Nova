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

  it('keeps other object details readable', () => {
    expect(messageFromBotApiBody(409, {
      detail: { error: 'bot is Level 0 -- fully dark', reason: 'BOT_L0_DARK' },
    })).toBe('bot is Level 0 -- fully dark -- BOT_L0_DARK');
  });
});
