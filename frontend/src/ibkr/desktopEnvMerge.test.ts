import { describe, expect, it } from 'vitest';
import {
  IBKR_CONNECT_DEFAULTS,
  ensureNovaApiKey,
  mergeMissingEnvKeys,
  parseEnvKeys,
  pickNovaApiKey,
  pickNovaEnvPath,
} from '../../electron/envMerge.mjs';

describe('desktop envMerge', () => {
  it('adds IBKR_ENABLED when the stub .env only has Alpaca keys', () => {
    const stub = [
      'APCA_API_KEY_ID=abc',
      'IBKR_GATEWAY_MODE=live',
      '',
    ].join('\n');
    const out = mergeMissingEnvKeys(stub, IBKR_CONNECT_DEFAULTS);
    const keys = parseEnvKeys(out);
    expect(keys.has('IBKR_ENABLED')).toBe(true);
    expect(out).toMatch(/IBKR_ENABLED=true/);
    expect(out).toMatch(/IBKR_LIVE_PORT=4001/);
    expect(out).not.toMatch(/IBKR_ORDERS_ENABLED/);
    expect(out).not.toMatch(/IBKR_LIVE_TRADING_CONFIRMED/);
  });

  it('does not overwrite an explicit IBKR_ENABLED=false', () => {
    const out = mergeMissingEnvKeys('IBKR_ENABLED=false\n', IBKR_CONNECT_DEFAULTS);
    expect(out).toMatch(/^IBKR_ENABLED=false\n/);
    expect(out.match(/IBKR_ENABLED=/g)?.length).toBe(1);
    expect(out).not.toMatch(/IBKR_ENABLED=true/);
  });

  it('provisions NOVA_API_KEY once and keeps an existing value', () => {
    const created = ensureNovaApiKey('APCA_API_KEY_ID=abc\n', () => 'generated-key');
    expect(created.created).toBe(true);
    expect(created.key).toBe('generated-key');
    expect(created.text).toMatch(/NOVA_API_KEY=generated-key/);

    const again = ensureNovaApiKey(created.text, () => 'other');
    expect(again.created).toBe(false);
    expect(again.key).toBe('generated-key');
    expect(again.text.match(/NOVA_API_KEY=/g)?.length).toBe(1);
  });

  it('picks the API process/repo key instead of inventing a userData key', () => {
    expect(pickNovaApiKey({
      processKey: 'process-secret',
      envPathKey: 'from-nova-env-path',
      repoKey: 'repo-secret',
      userDataKey: 'desktop-secret',
      packaged: false,
    })).toEqual({ key: 'process-secret', source: 'process' });

    const unpackaged = pickNovaApiKey({
      processKey: '',
      envPathKey: '',
      repoKey: 'repo-secret',
      userDataKey: 'other-generated',
      packaged: false,
    });
    expect(unpackaged).toEqual({ key: 'repo-secret', source: 'repo' });

    const packaged = pickNovaApiKey({
      processKey: '',
      envPathKey: '',
      repoKey: '',
      userDataKey: 'desktop-secret',
      packaged: true,
    });
    expect(packaged).toEqual({ key: 'desktop-secret', source: 'userdata' });

    const envPath = pickNovaApiKey({
      processKey: '',
      envPathKey: 'from-nova-env-path',
      repoKey: 'repo-secret',
      userDataKey: 'desktop-secret',
      packaged: true,
    });
    expect(envPath).toEqual({ key: 'from-nova-env-path', source: 'env_path' });

    const missing = pickNovaApiKey({
      processKey: '',
      envPathKey: '',
      repoKey: '',
      userDataKey: '',
      packaged: true,
    });
    expect(missing).toEqual({ key: '', source: 'missing' });
  });

  it('points NOVA_ENV_PATH at the file that owns the picked key', () => {
    expect(pickNovaEnvPath({
      source: 'repo',
      repoEnv: '/repo/.env',
      userEnv: '/user/.env',
      packaged: false,
    })).toBe('/repo/.env');
    expect(pickNovaEnvPath({
      source: 'userdata',
      repoEnv: '',
      userEnv: '/user/.env',
      packaged: true,
    })).toBe('/user/.env');
    expect(pickNovaEnvPath({
      source: 'missing',
      repoEnv: '/repo/.env',
      userEnv: '/user/.env',
      packaged: false,
    })).toBe('/repo/.env');
  });
});
