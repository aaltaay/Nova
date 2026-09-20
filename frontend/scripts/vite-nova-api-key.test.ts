import { describe, expect, it } from 'vitest';
import { readDevNovaApiKey, shouldInjectDevNovaApiKey } from './vite-nova-api-key';

describe('shouldInjectDevNovaApiKey', () => {
  it('injects for a real dev server', () => {
    expect(shouldInjectDevNovaApiKey({ command: 'serve', mode: 'development' })).toBe(true);
  });

  it('does not inject under Vitest, which also resolves the config as serve', () => {
    expect(
      shouldInjectDevNovaApiKey({ command: 'serve', mode: 'development', vitest: 'true' }),
    ).toBe(false);
  });

  it('does not inject in test mode', () => {
    expect(shouldInjectDevNovaApiKey({ command: 'serve', mode: 'test' })).toBe(false);
  });

  it('does not inject for a production build', () => {
    expect(shouldInjectDevNovaApiKey({ command: 'build', mode: 'production' })).toBe(false);
  });
});

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
