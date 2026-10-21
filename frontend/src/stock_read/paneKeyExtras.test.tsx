/**
 * @vitest-environment jsdom
 *
 * Sections another layer adds to a pane's Key (Ahead's zone, ADR 065): per chart, listed first, taken back on null.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { IChartApi } from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChartKey, keyCardMaxHeight, PaneKeyOnly } from './ChartKey';
import { KEY_CARD_MIN_PX, KEY_CARD_PANE_MARGIN_PX } from './constants';
import { paneKeySections, publishPaneKeySection, usePaneKeySections } from './paneKeyExtras';
import type { KeySection } from './paneKeyRows';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const SECTION: KeySection = {
  title: 'Ahead (AI view, not data)',
  rows: [
    { swatch: 'paths', color: '#c7d2fe', label: 'Paths', text: '16 of 200 possible paths' },
    { swatch: 'hatch', color: '#262c3d', fill: '#1b2030', label: 'Hatched zone', text: 'drawn, never recorded' },
    { swatch: 'band', color: '#93a4d6', fill: 'linear-gradient(red, blue)', label: 'Likely range', text: 'inner half' },
  ],
};

function Probe({ chart }: { chart: IChartApi }) {
  const extra = usePaneKeySections(chart);
  return <ChartKey sections={[...extra, { title: 'Setups', rows: [] }]} testId="key" />;
}

describe('pane Key sections from other layers', () => {
  it('belong to one chart, list first, and go when taken back', () => {
    const a = {} as IChartApi;
    const b = {} as IChartApi;
    render(<Probe chart={a} />);
    act(() => publishPaneKeySection(a, 'ahead', SECTION));
    expect(paneKeySections(b)).toEqual([]);
    const titles = [...screen.getByTestId('key-card').querySelectorAll('.sr-key__title')].map(t => t.textContent);
    expect(titles).toEqual(['Ahead (AI view, not data)', 'Setups']);
    // The paths swatch is drawn paths, the hatch a striped patch, the band its own fill.
    const card = screen.getByTestId('key-card');
    expect(card.querySelector('svg.sr-key__swatch--paths')).not.toBeNull();
    const swatches = [...card.querySelectorAll<HTMLElement>('i.sr-key__swatch')];
    expect(swatches[0].style.background).toContain('repeating-linear-gradient');
    expect(swatches[1].style.background).toContain('linear-gradient');
    act(() => publishPaneKeySection(a, 'ahead', null));
    expect(paneKeySections(a)).toEqual([]);
    expect(screen.getByTestId('key-card').textContent).not.toContain('Ahead');
  });

  it("keeps another layer's Key on a pane with no read, and shows nothing when no layer adds one", () => {
    const view = render(<PaneKeyOnly sections={[SECTION]} testId="stock-read-key-full" />);
    expect(screen.getByTestId('stock-read-key-full-only').className).toBe('sr-pane-top');
    expect(screen.getByTestId('stock-read-key-full-card').textContent).toContain('Ahead (AI view, not data)');
    view.unmount();
    render(<PaneKeyOnly sections={[]} testId="stock-read-key-full" />);
    expect(screen.queryByTestId('stock-read-key-full')).toBeNull();
  });
});

describe("the Key's card fits its pane", () => {
  it('runs from under the chip to just above the pane bottom, never under its floor, and waits for a laid-out pane', () => {
    expect(keyCardMaxHeight(30, { top: 0, bottom: 500 })).toBe(500 - 30 - KEY_CARD_PANE_MARGIN_PX);
    expect(keyCardMaxHeight(30, { top: 0, bottom: 100 })).toBe(KEY_CARD_MIN_PX);
    expect(keyCardMaxHeight(30, { top: 0, bottom: 0 })).toBeNull();
  });

  it('measures the pane as the card opens and caps the card at what the pane leaves it', () => {
    const rect = (top: number, bottom: number) => ({ top, bottom, left: 0, right: 600, width: 600,
      height: bottom - top, x: 0, y: top, toJSON: () => ({}) }) as DOMRect;
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      if (this.dataset.pane === 'true') return rect(100, 520);
      if (this.classList.contains('sr-key')) return rect(104, 122);
      return rect(0, 0);
    });
    render(
      <div data-pane="true">
        <div className="sr-pane-top"><ChartKey sections={[SECTION]} testId="key" /></div>
      </div>,
    );
    expect(screen.getByTestId('key-card').style.maxHeight).toBe('');
    fireEvent.pointerEnter(screen.getByTestId('key'));
    expect(screen.getByTestId('key-card').style.maxHeight).toBe(`${520 - 122 - KEY_CARD_PANE_MARGIN_PX}px`);
    // Pressing the chip measures again (the pane may have been resized).
    fireEvent.click(screen.getByTestId('key-chip'));
    expect(screen.getByTestId('key-card').style.maxHeight).toBe(`${520 - 122 - KEY_CARD_PANE_MARGIN_PX}px`);
  });
});
