/**
 * The heat map view (ADR 061): the Trader toolbar's switch swaps it in and out, its own switch goes back, the window
 * and dot-size buttons save the choice, and with no book it says why instead of a blank black screen.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HeatMapToolbar, useHeatMapShown } from './HeatMapToolbar';
import { heatCapLog, HeatMapView } from './HeatMapView';
import { HEAT_PREFS_DEFAULT, heatPrefs, setHeatPrefs } from './heatMapPrefs';
import { resetAllHeatForTests } from './heatStore';

function Probe() {
  return <span data-testid="shown">{useHeatMapShown() ? 'heat' : 'charts'}</span>;
}

describe('HeatMapView', () => {
  let root: Root;
  let mount: HTMLDivElement;

  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'Date'] });
    setHeatPrefs({ ...HEAT_PREFS_DEFAULT });
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
    vi.useRealTimers();
    vi.restoreAllMocks();
    resetAllHeatForTests();
    localStorage.clear();
  });

  it('one click swaps the charts for the heat map, one click on its own switch brings them back', () => {
    act(() => root.render(<><HeatMapToolbar /><Probe /></>));
    const toggle = mount.querySelector('[data-testid="heat-map-toggle"]') as HTMLButtonElement;
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    act(() => toggle.click());
    expect(mount.querySelector('[data-testid="shown"]')!.textContent).toBe('heat');
    act(() => root.render(<><HeatMapView symbol="glnd" active /><Probe /></>));
    const back = mount.querySelector('[data-testid="heat-map-back"]') as HTMLButtonElement;
    expect(back.getAttribute('aria-pressed')).toBe('true');
    act(() => back.click());
    expect(mount.querySelector('[data-testid="shown"]')!.textContent).toBe('charts');
  });

  it('saves the window and the dot size the operator picks', () => {
    act(() => root.render(<HeatMapView symbol="GLND" active />));
    const fifteen = [...mount.querySelectorAll('button')].find((b) => b.textContent === '15 min')!;
    act(() => fifteen.click());
    expect(heatPrefs().windowSec).toBe(900);
    expect(fifteen.getAttribute('aria-pressed')).toBe('true');
    const dots = mount.querySelector('[data-testid="heat-map-dots"]') as HTMLButtonElement;
    expect(dots.textContent).toBe('Dots: 1k+ shares');
    act(() => dots.click());
    expect(heatPrefs().minDot).toBe(2000);
  });

  it("says it is waiting for the stock's Level 2 instead of showing a blank screen", () => {
    act(() => root.render(<HeatMapView symbol="GLND" active />));
    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(mount.querySelector('[role="status"]')!.textContent).toContain("Waiting for GLND's Level 2");
  });

  it('maps brightness to the shares that read red (45 is near 37,000 shares)', () => {
    expect(10 ** heatCapLog(45)).toBeGreaterThan(30_000);
    expect(10 ** heatCapLog(45)).toBeLessThan(45_000);
    expect(heatCapLog(100)).toBeLessThan(heatCapLog(0));
  });
});
