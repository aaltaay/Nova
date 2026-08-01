/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { isDevToolingNoise } from './reportClientError';

describe('isDevToolingNoise', () => {
  it('filters Vite send-before-connect', () => {
    expect(
      isDevToolingNoise(
        'send was called before connect',
        'Error: send was called before connect\n    at Object.send (http://127.0.0.1:5173/@vite/client:384:15)',
      ),
    ).toBe(true);
  });

  it('filters Vite undefined send cascade', () => {
    expect(
      isDevToolingNoise(
        "Cannot read properties of undefined (reading 'send')",
        "TypeError: Cannot read properties of undefined (reading 'send')\n    at Object.send (http://localhost:5173/@vite/client:438:7)",
      ),
    ).toBe(true);
  });

  it('filters TradingView object disposed', () => {
    expect(isDevToolingNoise('Uncaught Error: Object is disposed', null)).toBe(true);
  });

  it('filters provider shell mount races', () => {
    expect(
      isDevToolingNoise(
        'useModuleVisibility must be used within ModuleVisibilityProvider',
        null,
      ),
    ).toBe(true);
  });

  it('keeps real product errors', () => {
    expect(
      isDevToolingNoise(
        'Cannot read properties of undefined (reading \'symbol\')',
        'TypeError: ...\n    at TickerDetail.tsx:42:10',
      ),
    ).toBe(false);
  });
});
