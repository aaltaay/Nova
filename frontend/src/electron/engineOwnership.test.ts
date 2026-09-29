import { describe, expect, it } from 'vitest';
import { ownershipPrompt, packagedEngineDecision } from '../../electron/engineOwnership.mjs';

describe('packaged backend ownership', () => {
  it('silently reuses only a matching packaged engine', () => {
    expect(packagedEngineDecision({
      deskTag: 'v1027',
      engine: { frozen: true, release_tag: 'v1027' },
    })).toBe('reuse');
    expect(packagedEngineDecision({
      deskTag: 'v1027',
      engine: { frozen: true, release_tag: 'v1025' },
    })).toBe('ask');
  });

  it('never silently adopts a checkout or an engine with unknown ownership', () => {
    expect(packagedEngineDecision({
      deskTag: 'v1027',
      engine: { frozen: false, release_tag: 'v1027', root: 'C:\\Nova' },
    })).toBe('ask');
    expect(packagedEngineDecision({ deskTag: 'v1027', engine: {} })).toBe('ask');
    // A healthy port whose diagnostics did not answer: never spawn a second engine over it.
    expect(packagedEngineDecision({ deskTag: 'v1027', engine: null })).toBe('ask');
  });

  it('explains the mismatch and keeps packaged retry as the default', () => {
    const prompt = ownershipPrompt({
      deskTag: 'v1027',
      engine: { frozen: false, release_tag: 'v1025', root: 'C:\\Nova' },
    });
    expect(prompt.defaultId).toBe(0);
    expect(prompt.cancelId).toBe(2);
    expect(prompt.message).toContain('Nova v1027');
    expect(prompt.message).toContain('backend v1025');
    expect(prompt.detail).toContain('Stop the other Nova backend');
  });
});
