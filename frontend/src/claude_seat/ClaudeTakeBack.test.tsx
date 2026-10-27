/** @vitest-environment jsdom */
/**
 * A hidden tab's line lent to Claude (ADR 068 decision 14, approved design v3): the pane's words in Claude's violet,
 * a right-click that offers Take my Level 2 back from Claude, the press that reaches `/take-back` and asks the tab's
 * panes for their lines now, a refusal said in the backend's words, and the pill's words while it lasts.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LENT_LINE_RECALL_EVENT } from '../constantGroups/market_ui';
import { ClaudeLentWords, ClaudeTakeBackRow, takeBackHint } from './ClaudeTakeBack';
import { eventWords, lineRow, pillTone } from './claudeSeatWords';
import { resetClaudeSeatForTests, setClaudeSeatForTests } from './claudeSeatStore';
import { seatStatus } from './claudeSeatFixtures';
import type { ClaudeSeatStatus } from './types';

function lentFromSmpl(over: Partial<ClaudeSeatStatus> = {}): ClaudeSeatStatus {
  const s = seatStatus({ events: [], ...over });
  return { ...s, state: 'in_trade', symbol: 'RUNR', positions: [{ symbol: 'RUNR', qty: 300, mark: 6.86 }],
    line: { ...s.line, symbol: 'RUNR', depth: true, from_tab: 'SMPL' } };
}

let answer: { status: number; body: unknown };
const calls: { url: string; body: string | null }[] = [];

beforeEach(() => {
  calls.length = 0;
  answer = { status: 200, body: { ...lentFromSmpl(), line: { ...lentFromSmpl().line, from_tab: null, depth: false } } };
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if ((init?.method ?? 'GET') === 'GET') return new Response(JSON.stringify(lentFromSmpl()), { status: 200 });
    calls.push({ url: String(input), body: typeof init?.body === 'string' ? init.body : null });
    return new Response(JSON.stringify(answer.body), { status: answer.status });
  }));
  resetClaudeSeatForTests();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetClaudeSeatForTests();
});

describe("a tab's line lent to Claude", () => {
  it('the pane says it in violet; a right-click offers the one way back', () => {
    render(<ClaudeLentWords symbol="smpl" text="Level 2 lent to Claude (in a trade on RUNR)" testId="lent"
      className="pane" />);
    act(() => setClaudeSeatForTests(lentFromSmpl()));
    const pane = screen.getByTestId('lent');
    expect(pane.className).toContain('claude-lent');
    expect(pane.textContent).toContain('Level 2 lent to Claude (in a trade on RUNR)');
    expect(screen.queryByTestId('claude-take-back')).toBeNull();          // no button until the right-click
    fireEvent.contextMenu(pane, { clientX: 40, clientY: 50 });
    const row = screen.getByTestId('claude-take-back');
    expect(row.textContent).toContain('Take my Level 2 back from Claude');
    expect(row.textContent).toContain('Its stop and sell on RUNR keep resting');
  });

  it('the press takes it back and asks the tab for its lines at once', async () => {
    const recalled: string[] = [];
    const hear = (e: Event) => recalled.push((e as CustomEvent<{ symbol: string }>).detail.symbol);
    window.addEventListener(LENT_LINE_RECALL_EVENT, hear);
    const done = vi.fn();
    render(<ClaudeTakeBackRow symbol="SMPL" onDone={done} />);
    act(() => setClaudeSeatForTests(lentFromSmpl()));
    fireEvent.click(screen.getByTestId('claude-take-back'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls[0].url).toMatch(/\/api\/agent\/trader\/take-back$/);
    expect(JSON.parse(calls[0].body ?? '{}')).toEqual({ symbol: 'SMPL' });
    expect(recalled).toEqual(['SMPL']);
    window.removeEventListener(LENT_LINE_RECALL_EVENT, hear);
  });

  it("a refusal stays on screen in the backend's words", async () => {
    answer = { status: 404, body: { detail: { reason: 'AGENT_NOT_MINE', error: "SMPL's Level 2 is not lent to Claude" } } };
    const done = vi.fn();
    render(<ClaudeTakeBackRow symbol="SMPL" onDone={done} />);
    act(() => setClaudeSeatForTests(lentFromSmpl()));
    fireEvent.click(screen.getByTestId('claude-take-back'));
    expect((await screen.findByTestId('claude-take-back-error')).textContent).toContain('not lent to Claude');
    expect(done).not.toHaveBeenCalled();
  });

  it('a tab Claude does not hold shows no row', () => {
    render(<ClaudeTakeBackRow symbol="SPIK" onDone={() => {}} />);
    act(() => setClaudeSeatForTests(lentFromSmpl()));
    expect(screen.queryByTestId('claude-take-back')).toBeNull();
  });

  it('the panel, the toasts and the pill say where the line came from and what happens after', () => {
    expect(lineRow(lentFromSmpl())).toBe(
      "Level 2 + Time & Sales on RUNR · your SMPL tab's line (right-click the tab to take it back)");
    expect(eventWords({ at: 1, kind: 'tab_line_back', text: "You took SMPL's line back from Claude" }))
      .toBe("You took SMPL's line back from Claude");
    expect(eventWords({ at: 1, kind: 'tab_line', text: "took your hidden SMPL tab's line · watching RUNR" }))
      .toBe("Claude took your hidden SMPL tab's line · watching RUNR");
    const back = lentFromSmpl();
    expect(pillTone({ ...back, line: { ...back.line, depth: false, from_tab: null } })).toBe('wait');
    expect(pillTone(back)).toBe('on');
    expect(takeBackHint('RUNR', false)).toBe('Claude stays on and waits for another line.');
  });
});
