import { describe, expect, it } from 'vitest';
import { readDevNovaApiKey } from './vite-nova-api-key';

describe('readDevNovaApiKey', () => {
  it('prefers VITE_NOVA_API_KEY over NOVA_API_KEY', () => {
    expect(readDevNovaApiKey({
      VITE_NOVA_API_KEY: 'vite-key',
      NOVA_API_KEY: 'repo-key',
    })).toBe('vite-key');
  });

  it('maps repo NOVA_API_KEY when Vite is unset', () => {
    expect(readDevNovaApiKey({ NOVA_API_KEY: 'repo-key' })).toBe('repo-key');
  });

  it('returns empty when neither is set', () => {
    expect(readDevNovaApiKey({})).toBe('');
  });
});
