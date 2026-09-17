import { describe, expect, it } from 'vitest';
import { skipApiSidecar } from '../../electron/sidecarSkip.mjs';

describe('skipApiSidecar', () => {
  it('is off when the env is missing or empty', () => {
    expect(skipApiSidecar({})).toBe(false);
    expect(skipApiSidecar({ NOVA_SKIP_API_SIDECAR: '' })).toBe(false);
    expect(skipApiSidecar({ NOVA_SKIP_API_SIDECAR: '0' })).toBe(false);
    expect(skipApiSidecar({ NOVA_SKIP_API_SIDECAR: 'no' })).toBe(false);
  });

  it('is on for 1 / true / yes (any case, trimmed)', () => {
    expect(skipApiSidecar({ NOVA_SKIP_API_SIDECAR: '1' })).toBe(true);
    expect(skipApiSidecar({ NOVA_SKIP_API_SIDECAR: ' true ' })).toBe(true);
    expect(skipApiSidecar({ NOVA_SKIP_API_SIDECAR: 'YES' })).toBe(true);
  });
});
