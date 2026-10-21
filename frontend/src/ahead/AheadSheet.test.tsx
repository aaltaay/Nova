/**
 * @vitest-environment jsdom
 *
 * The Ahead panel (ADR 061): each card per state, scores never read as zero, the scope and the switch kept in prefs.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import readyWire from './__fixtures__/answer_ready.json';
import statusWire from './__fixtures__/status_ready.json';
import { publishAheadScene } from './AheadChartLayer';
import { normalizeAnswer, normalizeStatus } from './aheadApi';
import { AHEAD_WORDS } from './aheadConstants';
import { readAheadPrefs, reloadAheadPrefsForTesting } from './aheadPrefs';
import { AheadSheet } from './AheadSheet';
import { openAheadSheet, publishAhead, resetAheadStoreForTesting } from './aheadStore';
import { sampleScene } from './aheadTestKit';
import type { AheadStatus, AheadTrigger, AheadWalls } from './aheadTypes';

let status: AheadStatus | null = null;
let statusProblem: string | null = null;
vi.mock('./useAheadStatus', () => ({ useAheadStatus: () => ({ status, problem: statusProblem }) }));

const SYM = 'XYZ';
const ready = () => normalizeAnswer(structuredClone(readyWire), SYM);
const statusReady = () => normalizeStatus(structuredClone(statusWire)) as AheadStatus;

const WALLS: AheadWalls = {
  above: { zoneId: 'z1', price: 4.84, label: 'double top' },
  below: { zoneId: 'z2', price: 4.5, label: 'double bottom' },
  first: { above: 0.27, below: 0.43, neither: 0.3 },
  nPaths: 16,
  byT: 1792500960,
  reason: null,
};

const TRIGGER: AheadTrigger = {
  family: 'flat_top', setupType: 'flat_top_breakout', state: 'armed', provisional: false, trigger: 4.7, entry: 4.7,
  stop: 4.55, target: 4.84, reach: 0.57, nReach: 9, first: { target: 0.31, stop: 0.25, open: 0.44 }, perPath: null,
  reason: null,
};

function show(scene = sampleScene({ walls: WALLS }), answer = ready()) {
  act(() => {
    publishAhead(SYM, { answer, problem: null });
    publishAheadScene(SYM, scene);
    openAheadSheet(SYM);
  });
  return render(<AheadSheet symbol={SYM} />);
}

beforeEach(() => {
  localStorage.clear();
  reloadAheadPrefsForTesting();
  status = statusReady();
  statusProblem = null;
});

afterEach(() => {
  cleanup();
  act(() => {
    resetAheadStoreForTesting();
    publishAheadScene(SYM, null);
  });
});

describe('AheadSheet', () => {
  it('is not there until opened', () => {
    render(<AheadSheet symbol={SYM} />);
    expect(screen.queryByTestId('ahead-sheet')).toBeNull();
  });

  it('shows which wall first as the chart counted it, marked as the AI view', () => {
    show();
    const card = screen.getByTestId('ahead-walls-card');
    expect(card.textContent).toContain('▲ 4.84 · double top');
    expect(screen.getByTestId('ahead-walls-bar').textContent).toBe('27%30%43%');
    expect(card.textContent).toContain(AHEAD_WORDS.aiTag);
    expect(card.textContent).toContain('distance, not a call on direction');
    expect(screen.getByTestId('ahead-walls-forecast').textContent).toBe(AHEAD_WORDS.sharesForecast);
  });

  it('shows the forecast volume against the real last 15 minutes', () => {
    show();
    expect(screen.getByTestId('ahead-volume-q50').textContent).toBe('120k');
    const card = screen.getByTestId('ahead-volume-card');
    expect(card.textContent).toContain('60k to 240k');
    expect(card.textContent).toContain(AHEAD_WORDS.forecast);
    expect(card.textContent).toContain(AHEAD_WORDS.volumeLast);
  });

  it("shows the forecaster's exam and a score not made yet as not scored, never zero", () => {
    show();
    expect(screen.getByTestId('ahead-exam-tag').textContent).toBe(AHEAD_WORDS.notPassedTag);
    expect(screen.getByTestId('ahead-exam-card').textContent).toContain('(should be near 80%)');
    expect(screen.getByTestId('ahead-report-range').textContent).toContain(AHEAD_WORDS.notScored);
    expect(screen.getByTestId('ahead-report-range').textContent).not.toMatch(/\b0(\.0+)?\b/);
    expect(screen.getByTestId('ahead-report-volume').textContent).toContain('0.40');
    expect(screen.getByTestId('ahead-report-band80').textContent).toContain('75%');
  });

  it('says "No exam yet." when the forecaster has run none', () => {
    status = { ...statusReady(), health: { ...statusReady().health!, exam: null } };
    const a = ready();
    show(sampleScene({ walls: WALLS }), { ...a, ai: { ...a.ai, exam: null } });
    expect(screen.getByTestId('ahead-exam-none').textContent).toBe(AHEAD_WORDS.examNone);
    expect(screen.queryByTestId('ahead-report-none')).toBeNull();
  });

  it('says why the exam and the report card are empty when the status could not be read', () => {
    status = null;
    statusProblem = AHEAD_WORDS.apiMissing;
    const a = ready();
    show(sampleScene({ walls: WALLS }), { ...a, ai: { ...a.ai, exam: null } });
    expect(screen.getByTestId('ahead-exam-none').textContent).toBe(AHEAD_WORDS.examUnknown(AHEAD_WORDS.apiMissing));
    expect(screen.getByTestId('ahead-report-none').textContent).toBe(AHEAD_WORDS.examUnknown(AHEAD_WORDS.apiMissing));
    expect(screen.getByTestId('ahead-sheet').textContent).not.toContain(AHEAD_WORDS.notScored);
  });

  it("says the forecaster's own reason when it is set up but its health is unknown, and no forecaster when none is", () => {
    status = { ...statusReady(), health: null, reason: 'could not connect to the forecaster' };
    const a = ready();
    show(sampleScene({ walls: WALLS }), { ...a, ai: { ...a.ai, exam: null } });
    const why = AHEAD_WORDS.examUnknown('could not connect to the forecaster');
    expect(screen.getByTestId('ahead-exam-none').textContent).toBe(why);
    expect(screen.getByTestId('ahead-report-none').textContent).toBe(why);
    cleanup();
    status = { ...statusReady(), configured: false, health: null, reason: 'NOVA_AHEAD_URL is not set' };
    show(sampleScene({ walls: WALLS }), { ...a, ai: { ...a.ai, exam: null } });
    expect(screen.getByTestId('ahead-exam-none').textContent).toBe(AHEAD_WORDS.noForecaster('NOVA_AHEAD_URL is not set'));
  });

  it('puts the reason on every AI card while the AI view is hidden', () => {
    show(sampleScene({ fan: null, walls: { ...WALLS, first: null }, words: [AHEAD_WORDS.hiddenNotPassed] }));
    expect(screen.getByTestId('ahead-sheet-state').textContent).toBe(AHEAD_WORDS.hiddenNotPassed);
    expect(screen.getByTestId('ahead-walls-reason').textContent).toBe(AHEAD_WORDS.hiddenNotPassed);
    expect(screen.getByTestId('ahead-volume-reason').textContent).toBe(AHEAD_WORDS.hiddenNotPassed);
    expect(screen.queryByTestId('ahead-volume-q50')).toBeNull();
  });

  it('says Ahead draws on the 1-minute chart when no 1-minute pane draws it', () => {
    act(() => openAheadSheet(SYM));
    render(<AheadSheet symbol={SYM} />);
    expect(screen.getByTestId('ahead-sheet-state').textContent).toBe(AHEAD_WORDS.onlyOneMinute);
  });

  it('keeps the scope and the "show before it has earned it" switch in prefs', () => {
    show(sampleScene({ walls: WALLS, triggers: { flat_top: TRIGGER, first_pullback: { ...TRIGGER, family: 'first_pullback',
      reach: null, first: null, reason: AHEAD_WORDS.noLane('first pullback') } } }));
    fireEvent.click(screen.getByTestId('ahead-scope-flat_top'));
    expect(readAheadPrefs().scope).toBe('flat_top');
    expect(screen.getByTestId('ahead-scope-flat_top').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('ahead-trigger-reach').textContent).toContain('57% of the 16 paths reach the buy-stop 4.70');
    expect(screen.getByTestId('ahead-trigger-bar').textContent).toBe('31%44%25%');
    expect(screen.getByTestId('ahead-trigger-forecast').textContent).toBe(AHEAD_WORDS.sharesForecast);
    fireEvent.click(screen.getByTestId('ahead-scope-first_pullback'));
    expect(screen.getByTestId('ahead-trigger-reason').textContent).toBe('No first pullback in play on the 1-minute chart.');
    fireEvent.click(screen.getByTestId('ahead-scope-lines'));
    expect(screen.getByTestId('ahead-lines-card')).toBeTruthy();
    const sw = screen.getByTestId('ahead-unearned');
    expect(sw.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(sw);
    expect(readAheadPrefs().unearned).toBe(true);
    expect(screen.getByTestId('ahead-unearned').getAttribute('aria-checked')).toBe('true');
  });

  it('closes on Escape and on ✕', () => {
    show();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('ahead-sheet')).toBeNull();
    act(() => openAheadSheet(SYM));
    fireEvent.click(screen.getByTestId('ahead-sheet-close'));
    expect(screen.queryByTestId('ahead-sheet')).toBeNull();
  });
});
