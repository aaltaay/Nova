/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { EarningsDots, earningsDotsTitle } from './EarningsDots';

describe('earningsDotsTitle', () => {
  it('names the date and after-close session', () => {
    expect(earningsDotsTitle('2026-08-27', 'amc', false)).toBe(
      'Earnings 2026-08-27 (after close)',
    );
  });

  it('marks estimated dates', () => {
    expect(earningsDotsTitle('2026-08-27', 'bmo', true)).toBe(
      'Earnings 2026-08-27 (before open, estimated)',
    );
  });

  it('falls back when there is no date', () => {
    expect(earningsDotsTitle(null, null, null)).toBe('No earnings date');
  });
});

describe('EarningsDots', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  async function renderDots(props: {
    offset: number | null;
    earningsDate?: string | null;
    session?: 'bmo' | 'amc' | 'intraday' | null;
    estimated?: boolean | null;
  }) {
    await act(() => {
      root.render(
        <EarningsDots
          offset={props.offset}
          earningsDate={props.earningsDate ?? null}
          session={props.session ?? null}
          estimated={props.estimated ?? false}
        />,
      );
    });
  }

  it('lights tomorrow / today / yesterday in order', async () => {
    await renderDots({ offset: 1, earningsDate: '2026-08-28', session: 'bmo' });
    const dots = container.querySelectorAll('.earnings-dot');
    expect(dots).toHaveLength(3);
    expect(dots[0].classList.contains('lit')).toBe(true);
    expect(dots[1].classList.contains('lit')).toBe(false);
    expect(dots[2].classList.contains('lit')).toBe(false);

    await renderDots({ offset: 0, earningsDate: '2026-08-27', session: 'amc' });
    const today = container.querySelectorAll('.earnings-dot');
    expect(today[1].classList.contains('lit')).toBe(true);

    await renderDots({ offset: -1, earningsDate: '2026-08-26', session: 'amc' });
    const yest = container.querySelectorAll('.earnings-dot');
    expect(yest[2].classList.contains('lit')).toBe(true);
  });

  it('keeps all three dots dim when there is no window hit', async () => {
    await renderDots({ offset: null });
    const dots = container.querySelectorAll('.earnings-dot');
    expect(dots).toHaveLength(3);
    expect([...dots].every(d => !d.classList.contains('lit'))).toBe(true);
    expect(container.querySelector('.earnings-dots')?.getAttribute('title')).toBe(
      'No earnings date',
    );
  });

  it('puts the earnings date on hover', async () => {
    await renderDots({
      offset: 0,
      earningsDate: '2026-08-27',
      session: 'amc',
      estimated: true,
    });
    expect(container.querySelector('.earnings-dots')?.getAttribute('title')).toBe(
      'Earnings 2026-08-27 (after close, estimated)',
    );
  });
});
