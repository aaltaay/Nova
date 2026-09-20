/**
 * @vitest-environment jsdom
 *
 * #357: the sample desk renders its own account figures with no backend.
 * The Playwright spec covers this end to end; this pins the two pieces it
 * depends on (chrome resolution + fixture formatting) without a browser.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlobalBarAccountCluster } from '../components/GlobalBarAccountCluster';
import { resolveAccountChromeState } from '../components/globalBarAccountChrome';
import { SAMPLE_IBKR_ACCOUNT_STATE, SAMPLE_SUMMARY } from './sampleAccount';
import { isSampleView } from './sampleNav';

const here = dirname(fileURLToPath(import.meta.url));

/** The exact expression GlobalAppBar feeds resolveAccountChromeState. */
function chromeForSampleDesk(ibkrConnected: boolean) {
  return resolveAccountChromeState({
    ibkrConnected: Boolean(ibkrConnected) || isSampleView(),
    summaryConnected: SAMPLE_SUMMARY.connected,
    loading: SAMPLE_IBKR_ACCOUNT_STATE.loading,
    error: SAMPLE_IBKR_ACCOUNT_STATE.error,
  });
}

describe('sample desk account chrome', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.history.replaceState({}, '', '/');
  });

  it('is ready on the sample route even with Gateway reported down', () => {
    // CI and the marketing desk both run with no Nova API, so ibkrConnected
    // is false there; the header must not say "IBKR offline" anyway.
    window.history.replaceState({}, '', '/?view=sample');
    expect(chromeForSampleDesk(false)).toBe('ready');
  });

  it('is the expression GlobalAppBar actually passes', () => {
    // Binds the cases above to the real header: the chrome fix is one line in
    // GlobalAppBar, and nothing else would catch it being reverted.
    const src = readFileSync(join(here, '..', 'components', 'GlobalAppBar.tsx'), 'utf8');
    expect(src).toMatch(/import \{ isSampleView \} from '\.\.\/sample_data\/sampleNav'/);
    expect(src).toMatch(
      /resolveAccountChromeState\(\{[\s\S]*?ibkrConnected: Boolean\(ibkrConnected\) \|\| isSampleView\(\)/,
    );
  });

  it('still reports offline on a live route with Gateway down', () => {
    window.history.replaceState({}, '', '/');
    expect(chromeForSampleDesk(false)).toBe('offline');
  });

  it('renders Day P&L and Net Liq from the sample fixture', () => {
    window.history.replaceState({}, '', '/?view=sample');
    act(() => {
      root.render(
        <GlobalBarAccountCluster
          accountChrome={chromeForSampleDesk(false)}
          accountError={null}
          summary={SAMPLE_SUMMARY}
          orders={SAMPLE_IBKR_ACCOUNT_STATE.orders}
          workingCount={0}
          openMenu={null}
          setOpenMenu={vi.fn()}
          accountCardId="card"
          workingMenuId="working"
          closedOrders={[]}
          traderActive={false}
          closeTraderView={vi.fn()}
          refresh={vi.fn()}
        />,
      );
    });

    expect(container.querySelector('[data-testid="global-bar-offline"]')).toBeNull();
    expect(container.querySelector('[data-testid="global-bar-cluster"]')).toBeTruthy();
    expect(
      container.querySelector('[data-testid="global-bar-account-trigger"]')?.textContent,
    ).toContain('+$230.00');
    expect(
      container.querySelector('.global-app-bar__metric--netliq')?.textContent,
    ).toContain('$100,000.00');
  });
});
