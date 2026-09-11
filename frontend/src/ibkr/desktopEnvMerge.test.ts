import { describe, expect, it } from 'vitest';
import {
  IBKR_CONNECT_DEFAULTS,
  ensureNovaApiKey,
  mergeMissingEnvKeys,
  parseEnvKeys,
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
});
