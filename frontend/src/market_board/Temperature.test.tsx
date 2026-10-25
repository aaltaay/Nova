/**
 * @vitest-environment jsdom
 *
 * The small-cap temperature (ADR 053 amendment 2026-10-25): the climate card's label with the numbers behind it, a
 * stated reason when there is no label, and the Day Read's line that never counts as a check.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ClimateCard } from './ClimateCard';
import { DayReadCard } from './DayRead';
import { sampleMarketBoard } from './sampleMarket';
import { Temperature } from './Temperature';
import type { BlockPeriods, Heat } from './types';

const PERIODS = (climate: BlockPeriods['climate']): BlockPeriods =>
  ({ sectors: '1D', industries: '1D', climate, top: { kind: 'biggest', period: '1D' } });

afterEach(cleanup);

describe('the small-cap temperature', () => {
  it('labels the day and shows the runners and the money against the usual', () => {
    const c = sampleMarketBoard(PERIODS('1D')).climate;
    render(<ClimateCard c={c} onPeriod={() => {}} />);
    const card = screen.getByTestId('market-climate');
    expect(card.textContent).toContain('HOT DAY');
    const heat = within(card).getByTestId('market-heat');
    expect(heat.textContent).toContain('Up 100%+ ($2–20)');
    expect(heat.textContent).toContain('$1.4B');
    expect(heat.textContent).toContain('usual $580M · median of 20 sessions');
    fireEvent.click(within(heat).getByRole('button', { name: /the rule/ }));
    expect(within(heat).getByRole('note').textContent).toContain('2 or more up 100%');
  });

  it('draws a week as five sessions and a month with its score', () => {
    render(<ClimateCard c={sampleMarketBoard(PERIODS('7D')).climate} onPeriod={() => {}} />);
    expect(screen.getByTestId('market-climate').textContent).toContain('GOOD WEEK');
    expect(screen.getAllByRole('listitem')).toHaveLength(5);
    expect(screen.getByTestId('market-heat').textContent).toContain('3 hot · 2 warm · 0 cold');
    cleanup();
    render(<ClimateCard c={sampleMarketBoard(PERIODS('30D')).climate} onPeriod={() => {}} />);
    const heat = screen.getByTestId('market-heat');
    expect(screen.getByTestId('market-climate').textContent).toContain('HOT MONTH');
    expect(heat.textContent).toContain('score +21%');
    expect(heat.querySelectorAll('.is-none')).toHaveLength(2);            // two sessions Nova holds no board for
  });

  it('says why there is no label instead of guessing one', () => {
    const heat: Heat = {
      label: null, why: 'Nova recorded no Gainers board this session', price_min: 2, price_max: 20,
      days: [{ date: '2026-10-23', board: false, label: null, runners_100: null, money: null, usual_money: null,
        usual_days: 0, hold_pct: null }],
      hot: 0, warm: 0, cold: 0, labelled: 0, hold_pct: null, score_pct: null,
    };
    render(<Temperature heat={heat} period="1D" />);
    const el = screen.getByTestId('market-heat');
    expect(el.textContent).toContain('Nova recorded no Gainers board this session');
    expect(el.textContent).toContain('--');
    expect(el.textContent).not.toContain('$0');
  });

  it('puts the three words on top of the Day Read, apart from its checks', () => {
    const b = sampleMarketBoard(PERIODS('1D'));
    const read = { ...b.day_read, temperature: { day: 'cold' as const, week: 'choppy' as const, month: null } };
    render(<DayReadCard read={read} events={b.events} now={b.generated_at} />);
    const line = screen.getByTestId('market-day-read-temperature');
    expect(line.textContent).toBe('Small capscold daychoppy week-- month');
    expect(screen.getByTestId('market-day-read').textContent).toContain('5 of 6 checks green');   // the verdict is unchanged
    cleanup();
    render(<DayReadCard read={{ ...b.day_read, temperature: undefined }} events={b.events} now={b.generated_at} />);
    expect(screen.queryByTestId('market-day-read-temperature')).toBeNull();                    // an older backend
  });
});
