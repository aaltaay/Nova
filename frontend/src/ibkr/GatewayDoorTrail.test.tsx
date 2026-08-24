/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { GatewayDoorTrail } from './GatewayDoorTrail';

describe('GatewayDoorTrail', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          ok: true,
          events: [
            {
              schema_version: 1,
              ts: 1_700_000_000,
              actor: 'operator',
              event: 'click',
              requested: 'live',
              plan: 'start_ibc',
            },
            {
              schema_version: 1,
              ts: 1_700_000_010,
              actor: 'ibc',
              event: 'ibc_second_factor',
              note: 'Second Factor Authentication initiated',
            },
          ],
        }),
      })),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('renders IBC 2FA and Live click rows from the trail API', async () => {
    await act(async () => {
      root.render(<GatewayDoorTrail />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="gateway-door-trail"]')).toBeTruthy();
    expect(container.textContent).toContain('Second Factor / IBKR Mobile');
    expect(container.textContent).toContain('Click');
    expect(container.textContent).toContain('live');
  });
});
