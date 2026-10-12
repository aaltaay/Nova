/**
 * @vitest-environment jsdom
 *
 * Which target would have paid (#845): the read-out of every target choice side by side, read on arrival (another
 * schema or an unreadable choice is an error, never an empty table), asked only when opened, from a start date the
 * operator can move, with its stated cost and the backend's note when no choice leads yet.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BotTargetChoices } from './BotTargetChoices';
import { choiceLabel, parseTargetChoices } from './targetChoicesApi';

function readout(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1, from: '2026-10-13', setup_type: 'first_pullback', template: 'fp-default', cost: 0.01, min_n: 30,
    triggers: 12, scored: 11,
    choices: [
      { name: 'default', n: 11, wins: 6, win_pct: 54.5, mean_r: 0.31, sum_r: 3.41, mean_net_r: 0.24, sum_net_r: 2.64,
        fell_back: 0, open: 1 },
      { name: 'fixed_20c', n: 11, wins: 7, win_pct: 63.6, mean_r: 0.12, sum_r: 1.32, mean_net_r: 0.05, sum_net_r: 0.55,
        fell_back: 0, open: 0 },
      { name: 'hod', n: 9, wins: 2, win_pct: 22.2, mean_r: -0.4, sum_r: -3.6, mean_net_r: -0.47, sum_net_r: -4.23,
        fell_back: 2, open: 0 },
    ],
    leader: null,
    note: 'No leader: the fewest scored triggers of a choice is 9; the read-out names one from 30.',
    ...over,
  };
}

function stubFetch(body: unknown, status = 200) {
  const urls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  }));
  return urls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('the target read-out on the wire', () => {
  it('reads every choice, best first, and refuses another schema or a choice it cannot read', () => {
    const r = parseTargetChoices(readout());
    expect(r?.choices.map(c => c.name)).toEqual(['default', 'fixed_20c', 'hod']);
    expect(r).toMatchObject({ cost: 0.01, min_n: 30, triggers: 12, scored: 11, leader: null });
    expect(parseTargetChoices(readout({ schema_version: 2 }))).toBeNull();
    expect(parseTargetChoices(readout({ choices: [{ n: 3 }] }))).toBeNull();
    expect(parseTargetChoices(readout({ cost: undefined }))).toBeNull();
    expect(parseTargetChoices(null)).toBeNull();
  });

  it("names each choice in the menu's words, a short's mirrored -- never a multiple of the risk", () => {
    expect(['fixed_10c', 'fixed_30c', 'next_level', 'pullback_high', 'hod', 'default'].map(n => choiceLabel(n)))
      .toEqual(['+10c', '+30c', '1c under the next level', 'the pullback high', '1c under HOD', "the template's two targets"]);
    expect(['fixed_20c', 'hod', 'pullback_high', 'default'].map(n => choiceLabel(n, true)))
      .toEqual(['-20c', '1c over LOD', 'the bounce low', "the template's two covers"]);
  });
});

describe('Which target pays, on a setup card', () => {
  it('asks only when opened, then lays the choices out with the stated cost and the note', async () => {
    const urls = stubFetch(readout());
    render(<BotTargetChoices setup="first_pullback" />);
    expect(urls).toEqual([]);
    fireEvent.click(screen.getByTestId('bots-target-choices-toggle-first_pullback'));
    const table = await screen.findByTestId('bots-target-choices-table');
    expect(urls[0]).toMatch(/\/api\/setups\/target-choices\?from=2026-10-13&setup=first_pullback$/);
    const rows = within(table).getAllByRole('row').slice(1).map(r => [...r.querySelectorAll('td')].map(td => td.textContent));
    expect(rows[0]).toEqual(["the template's two targets", '11 +1 open', '54.5%', '+0.31R', '+3.41R', '+0.24R', '+2.64R', '0']);
    expect(rows[2]).toEqual(['1c under HOD', '9', '22.2%', '−0.40R', '−3.60R', '−0.47R', '−4.23R', '2']);
    expect(screen.getByTestId('bots-target-choices-cost-first_pullback').textContent)
      .toBe('12 triggers since 2026-10-13, 11 scored · net of $0.01 a share a fill · a leader needs 30 scored a choice');
    expect(screen.getByTestId('bots-target-choices-note-first_pullback').textContent).toMatch(/^No leader:/);
    expect(table.textContent).not.toMatch(/(?<![\d.])2R\b|2:1/);
  });

  it('marks the leader once the backend names one, and asks again from a new start date', async () => {
    const urls = stubFetch(readout({ leader: 'default', note: 'default leads on 30 or more scored triggers a choice.' }));
    render(<BotTargetChoices setup="bear_flag" short />);
    fireEvent.click(screen.getByTestId('bots-target-choices-toggle-bear_flag'));
    expect((await screen.findByTestId('bots-target-choice-default')).textContent).toMatch(/^the template's two covers · leads/);
    fireEvent.change(screen.getByTestId('bots-target-choices-from-bear_flag'), { target: { value: '2026-10-20' } });
    await waitFor(() => expect(urls.some(u => /from=2026-10-20&setup=bear_flag$/.test(u))).toBe(true));
  });

  it('says what went wrong instead of an empty table', async () => {
    stubFetch({ schema_version: 9 });
    render(<BotTargetChoices setup="first_pullback" />);
    fireEvent.click(screen.getByTestId('bots-target-choices-toggle-first_pullback'));
    expect((await screen.findByRole('alert')).textContent).toMatch(/shape this page cannot read/);
    expect(screen.queryByTestId('bots-target-choices-table')).toBeNull();
  });
});
