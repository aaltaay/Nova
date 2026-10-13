/**
 * @vitest-environment jsdom
 *
 * Runners per session, by theme (ADR 053 amendment 2026-10-13 evening; operator: "the runners per session is so
 * tiny no hover, no maximizing"): a hover card per session, a session with no record said as such, and a large
 * view that opens on a click or the corner button and closes on Escape, the backdrop or its close button.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { RUNNERS_NOT_RECORDED, RUNNERS_TIP_THEMES, THEME_OTHER_COLOR } from './constants';
import { axisTop, dayWords, RunnersChart, themesOf } from './RunnersChart';
import type { Climate } from './types';

const COLORS: Record<string, string> = { Biotechnology: '#30d158', Software: '#64d2ff' };
const color = (name: string) => COLORS[name] ?? THEME_OTHER_COLOR;

function climate(days: Climate['days'], sessions = 1): Climate {
  return {
    period: '1D', from: days[days.length - 1].date, to: days[days.length - 1].date, sessions, covered: sessions,
    lens: { board: 'gainers', rank_max: 50, price_min: 0.5 },
    counts: { up20: 0, up50: 0, up100: 0 }, per_day: null, baseline: null, temperature: null, days,
    theme: null, themes: [], gappers: { held: 0, total: 0, gone: 0, rate_pct: null, baseline_rate_pct: null },
    halts: { count: 0, last: null, by_side: null, by_side_why: '' }, top: [],
  };
}

const DAYS: Climate['days'] = [
  { date: '2026-10-08', source: null, total: null, themes: {} },
  { date: '2026-10-09', source: 'recorded', total: 6, themes: { Biotechnology: 4, Software: 2 } },
  { date: '2026-10-12', source: 'recorded', total: 0, themes: {} },
  { date: '2026-10-13', source: 'recorded', total: 9, themes: { Software: 5, Biotechnology: 3, Shipping: 1 } },
];

afterEach(cleanup);

describe('the runners chart on the card', () => {
  it('draws one column per session, the unrecorded one hatched and with no theme bars', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    expect(screen.getByTestId('market-runners').textContent).toContain('4 sessions');
    const none = screen.getByTestId('runners-day-2026-10-08');
    expect(none.querySelectorAll('rect.mk-runners__none')).toHaveLength(1);
    expect(none.querySelectorAll('rect[fill^="#"]')).toHaveLength(0);
    const today = screen.getByTestId('runners-day-2026-10-13');
    expect([...today.querySelectorAll('rect[fill^="#"]')].map((r) => r.getAttribute('fill')))
      .toEqual(['#64d2ff', '#30d158', THEME_OTHER_COLOR]);       // most runners at the bottom
  });

  it('says a session’s runners by theme on hover, and hides it on leave', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    expect(screen.queryByTestId('runners-tip')).toBeNull();
    fireEvent.mouseEnter(screen.getByTestId('runners-hit-2026-10-13'));
    const tip = screen.getByTestId('runners-tip');
    expect(tip.textContent).toContain(dayWords('2026-10-13'));
    expect(tip.textContent).toContain('9 runners');
    expect([...tip.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['Software5', 'Biotechnology3', 'Shipping1']);
    fireEvent.mouseLeave(screen.getByTestId('runners-hit-2026-10-13').closest('.mk-runners__plot') as Element);
    expect(screen.queryByTestId('runners-tip')).toBeNull();
  });

  it('dims the other sessions while one is hovered', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    fireEvent.mouseEnter(screen.getByTestId('runners-hit-2026-10-09'));
    expect(screen.getByTestId('runners-day-2026-10-09').getAttribute('opacity')).not.toBe('0.35');
    expect(screen.getByTestId('runners-day-2026-10-13').getAttribute('opacity')).toBe('0.35');
  });

  it('says a session Nova did not record, never a zero', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    fireEvent.mouseEnter(screen.getByTestId('runners-hit-2026-10-08'));
    const tip = screen.getByTestId('runners-tip');
    expect(tip.textContent).toContain(RUNNERS_NOT_RECORDED);
    expect(tip.textContent).not.toContain('runners');
  });

  it('says a recorded session with no runner', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    fireEvent.mouseEnter(screen.getByTestId('runners-hit-2026-10-12'));
    expect(screen.getByTestId('runners-tip').textContent).toContain('no 20%+ runners');
  });

  it('lists the first themes and counts the rest', () => {
    const themes: Record<string, number> = {};
    for (let i = 0; i < RUNNERS_TIP_THEMES + 3; i += 1) themes[`Theme ${i}`] = 20 - i;
    const busy = [{ date: '2026-10-13', source: 'recorded', total: 999, themes }];
    render(<RunnersChart c={climate(busy)} color={color} period="day" />);
    fireEvent.mouseEnter(screen.getByTestId('runners-hit-2026-10-13'));
    const tip = screen.getByTestId('runners-tip');
    expect(tip.querySelectorAll('li')).toHaveLength(RUNNERS_TIP_THEMES);
    const rest = Object.values(themes).slice(RUNNERS_TIP_THEMES).reduce((a, v) => a + v, 0);
    expect(tip.textContent).toContain(`+ ${rest} in 3 more themes`);
  });

  it('frames the period the card shows and fades the sessions before it', () => {
    const { container } = render(<RunnersChart c={climate(DAYS, 1)} color={color} period="day" />);
    const lit = container.querySelector('rect.mk-climate__lit');
    const today = screen.getByTestId('runners-day-2026-10-13').querySelector('rect[fill^="#"]') as Element;
    expect(Number(lit?.getAttribute('x')) + 1).toBeCloseTo(Number(today.getAttribute('x')), 5);
    expect(screen.getByTestId('runners-day-2026-10-13').getAttribute('opacity')).toBe('1');
    expect(screen.getByTestId('runners-day-2026-10-09').getAttribute('opacity')).toBe('0.45');   // before it: faded
  });
});

describe('the large view', () => {
  it('opens on a click of the chart, with every date, each bar’s count and the axis', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    fireEvent.click(screen.getByTestId('runners-hit-2026-10-13'));
    const large = screen.getByTestId('market-runners-large');
    expect(large.getAttribute('role')).toBe('dialog');
    expect(large.parentElement?.parentElement).toBe(document.body);    // above the page, not clipped by it
    const ticks = [...large.querySelectorAll('text.mk-climate__tick')].map((t) => t.textContent);
    expect(ticks).toEqual(['Oct 8', 'Oct 9', 'Oct 12', 'Oct 13']);
    expect([...large.querySelectorAll('text.mk-runners__count')].map((t) => t.textContent)).toEqual(['6', '0', '9']);
    expect([...large.querySelectorAll('text.mk-runners__axis')].map((t) => t.textContent)).toEqual(['0', '5', '10']);
    expect(large.textContent).toContain('4 sessions, 3 recorded');
    expect(large.textContent).toContain('15 runners');
  });

  it('opens from the corner button and closes on its close button', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    fireEvent.click(screen.getByRole('button', { name: 'Open the runners chart large' }));
    expect(screen.getByTestId('market-runners-large')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Close the large chart' }));
    expect(screen.queryByTestId('market-runners-large')).toBeNull();
  });

  it('closes on Escape and on the backdrop, not on a click inside', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    fireEvent.click(screen.getByRole('button', { name: 'Open the runners chart large' }));
    act(() => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
    expect(screen.queryByTestId('market-runners-large')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Open the runners chart large' }));
    const large = screen.getByTestId('market-runners-large');
    fireEvent.mouseDown(large);
    expect(screen.getByTestId('market-runners-large')).toBeTruthy();
    fireEvent.mouseDown(large.parentElement as Element);
    expect(screen.queryByTestId('market-runners-large')).toBeNull();
  });

  it('hovers in the large view too, and names the coloured themes with the rest as one', () => {
    render(<RunnersChart c={climate(DAYS)} color={color} period="day" />);
    fireEvent.click(screen.getByRole('button', { name: 'Open the runners chart large' }));
    const large = screen.getByTestId('market-runners-large');
    const legend = large.querySelector('.mk-modal__legend') as HTMLElement;
    expect(legend.textContent).toContain('Biotechnology 7');
    expect(legend.textContent).toContain('Software 7');
    expect(legend.textContent).toContain('1 other themes 1');
    fireEvent.mouseEnter(within(large).getByTestId('runners-hit-2026-10-09'));
    expect(within(large).getByTestId('runners-tip').textContent).toContain('6 runners');
  });
});

describe('the chart’s rules', () => {
  it('rounds the axis top up to a readable number', () => {
    expect(axisTop(0)).toBe(1);
    expect(axisTop(9)).toBe(10);
    expect(axisTop(13)).toBe(20);
    expect(axisTop(22)).toBe(25);
    expect(axisTop(37)).toBe(40);
    expect(axisTop(48)).toBe(50);
    expect(axisTop(61)).toBe(100);
    expect(axisTop(140)).toBe(200);
  });

  it('stacks themes most runners first and drops empty ones', () => {
    expect(themesOf({ date: 'x', source: 'recorded', total: 3, themes: { A: 1, B: 2, C: 0 } })).toEqual([['B', 2], ['A', 1]]);
  });
});
