import { describe, expect, it, vi } from 'vitest';
import { BOT_ERROR_NEED_API_KEY } from '../constantGroups/bot';
import { fetchBotSession } from './api';

describe('bot api (read-only since ADR 072)', () => {
  it('raises a readable API-key error on 401 string details', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid or missing X-Nova-Api-Key' }),
    })));
    await expect(fetchBotSession()).rejects.toThrow(BOT_ERROR_NEED_API_KEY);
    vi.unstubAllGlobals();
  });
});
