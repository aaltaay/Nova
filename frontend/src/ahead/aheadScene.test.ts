import { beforeEach, describe, expect, it } from 'vitest';
import answerError from './__fixtures__/answer_error.json';
import answerNotEnoughBars from './__fixtures__/answer_not_enough_bars.json';
import answerNotSetUp from './__fixtures__/answer_not_set_up.json';
import answerOffline from './__fixtures__/answer_offline.json';
import answerPending from './__fixtures__/answer_pending.json';
import answerQuiet from './__fixtures__/answer_quiet.json';
import answerReady from './__fixtures__/answer_ready.json';
import answerWarming from './__fixtures__/answer_warming.json';
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import { chartHhmm, chartSec } from './aheadGeometry';
import { aheadScene, clearAheadSceneMemo } from './aheadScene';
import type { AheadSceneInput } from './aheadSceneTypes';
import type { AheadAnswer, AheadPrefs } from './aheadTypes';
import { sampleAhead } from './sampleAhead';

const ready = answerReady as unknown as AheadAnswer;
const BAR_T = ready.bar_t as number;
const ANCHOR = chartSec(BAR_T);

function candles(n = 240, lastT = ANCHOR) {
  return Array.from({ length: n }, (_, i) => ({ t: lastT - (n - 1 - i) * 60, c: 4.62 }));
}

const READ = {
  followed: true,
  followed_note: null,
  setups: [{
    setup_type: 'flat_top_breakout', state: 'armed', setup: { trigger: 4.7, entry: 4.71, stop: 4.55, target1: 4.84 },
    forming: null,
  }],
  level_map: {
    lines: {
      one_minute: [
        { id: 'sup', kind: 'support', state: 'holding', now_t: BAR_T, now_p: 4.6, slope: 0.01 },
        { id: 'res', kind: 'resistance', state: 'holding', now_t: BAR_T, now_p: 4.7, slope: -0.01 },
      ],
      five_minute: [],
    },
    intraday: [
      { id: 'top', lo: 4.84, hi: 4.85, label: '4.84 · double top', members: [{ kind: 'top' }] },
      { id: 'half', lo: 4.5, hi: 4.5, label: '$4.50 · double bottom', members: [{ kind: 'half' }, { kind: 'bottom' }] },
    ],
  },
} as unknown as AheadSceneInput['read'];

const PREFS: AheadPrefs = { shown: true, scope: 'all', unearned: false };

function input(over: Partial<AheadSceneInput> = {}): AheadSceneInput {
  return {
    symbol: 'XYZ', prefs: PREFS, paneIs1m: true, answer: ready, fetchProblem: null, read: READ, candles: candles(),
    macdOn: true, roomOk: true, replayEmpty: false, ...over,
  };
}

const passed: AheadAnswer = {
  ...ready,
  ai: { ...ready.ai, exam_passed: true, exam: ready.ai.exam && { ...ready.ai.exam, passed: true } },
};

const noAi = (s: ReturnType<typeof aheadScene>) => {
  expect(s.fan).toBeNull();
  expect(s.cloud).toEqual([]);
  expect(s.story).toEqual([]);
  expect(s.ghostVolume).toBeNull();
  expect(s.macd).toBeNull();
  // The legend keeps Nova's lines and the hatch only.
  expect(s.legend.map((r) => r.swatch)).toEqual(['dash', 'hatch']);
  expect(s.walls?.first ?? null).toBeNull();
  expect(s.triggers?.flat_top.reach ?? null).toBeNull();
  expect(s.chips).toEqual([]);
};

describe('the Ahead scene', () => {
  beforeEach(() => clearAheadSceneMemo());

  it('draws nothing while off, and says it draws on the 1-minute chart elsewhere', () => {
    expect(aheadScene(input({ prefs: { ...PREFS, shown: false } }))).toMatchObject({ on: false, words: [] });
    expect(aheadScene(input({ paneIs1m: false }))).toMatchObject({ on: false, words: [AHEAD_WORDS.onlyOneMinute] });
  });

  it('hides the AI view of a forecaster that has not passed its exam, and says why', () => {
    const s = aheadScene(input());
    noAi(s);
    expect(s.words[0]).toBe(AHEAD_WORDS.hiddenNotPassed);
    expect(s.zone?.tags.map((t) => t.text)).toEqual([AHEAD_WORDS.aiTag]);
    expect(s.lines).toHaveLength(2);
  });

  it('shows it, with its exam printed, once the viewer switches on Show before it has earned it', () => {
    const s = aheadScene(input({ prefs: { ...PREFS, unearned: true } }));
    expect(s.fan).toHaveLength(15);
    expect(s.fan?.[0]).toEqual({ k: 1, q10: 4.5963, q25: 4.6075, q50: 4.62, q75: 4.6325, q90: 4.6437 });
    // Every path in the soft cloud; three story paths over it, chosen by rule: the high, middle and low cases.
    expect(s.cloud).toEqual(ready.ai.paths?.close);
    expect(s.story.map((st) => st.label)).toEqual(['high case', 'middle case', 'low case']);
    expect(s.ghostVolume?.[14]).toEqual({ k: 15, q10: 3600, q50: 8000, q90: 16800 });
    expect(s.macd).toHaveLength(15);
    expect(s.legend.map((r) => r.swatch).filter((w) => w !== 'marks')).toEqual(['dash', 'band', 'paths', 'story', 'box',
      'hatch']);
    expect(s.legend.map((r) => r.text)).toContain('soft cloud = all 16 paths');
    expect(s.legend.map((r) => r.text)).toContain(AHEAD_WORDS.legendStoryCases(3, 16));
    expect(s.legend.map((r) => r.text).join(' ')).not.toContain('16 of');
    const tag = s.zone?.tags[1];
    expect(tag?.text).toContain('has not passed its exam');
    expect(tag?.text).toContain('Example only: made-up scope.');
    expect(tag?.fg).toBe(AHEAD_COLORS.notPassedFg);
    expect(s.walls?.first).not.toBeNull();
    expect(s.chips.map((c) => c.text)[0]).toMatch(/^▲ 4\.84 first · \d+% \(forecast\)$/);
    // The walls' chips are tied to their prices; "neither" to none (the drawing places it last, between the walls).
    expect(s.chips.map((c) => c.role)).toEqual(['wall', 'wall', 'neither', 'story', 'story', 'story']);
    // Each case's end label sits at its own last close.
    for (const st of s.story) {
      expect(s.chips.find((c) => c.text === st.label)?.p).toBe(st.points[st.points.length - 1]);
    }
    expect(s.legend.find((r) => r.swatch === 'paths')?.n).toBe(16);
    // If it breaks: no path closes over the top 4.84-4.85 (its chip says so); one dips under 4.50, with no wall beyond.
    expect(s.walls?.breaks?.above).toMatchObject({ share: 0, nBreak: 0, next: null, fail: null });
    expect(s.chips[0].sub).toEqual(['breaks 0%']);
    expect(s.walls?.breaks?.below?.nBreak).toBeGreaterThan(0);
    expect(s.walls?.breaks?.below?.next).toBeNull();
    expect(s.walls?.breaks?.below?.follow).toBeNull();
    // The odds-only words for a zone too narrow for the full chip.
    expect(s.chips.map((c) => c.short)[0]).toMatch(/^▲ \d+%$/);
    expect(s.examStatus).toEqual({ text: AHEAD_WORDS.notPassedTag, fg: AHEAD_COLORS.notPassedFg,
      bg: AHEAD_COLORS.notPassedBg });
    expect(s.words).toEqual([]);
  });

  it('says a passed exam with its scope and sample, never "EARNED"', () => {
    const s = aheadScene(input({ answer: passed }));
    expect(s.fan).not.toBeNull();
    const tag = s.zone?.tags[1];
    expect(tag?.text).toBe('passed its exam · Example only: made-up scope. · 10 days, 100 moments');
    expect(s.examStatus).toMatchObject({ text: AHEAD_WORDS.passedTag, fg: AHEAD_COLORS.passedFg });
    expect(JSON.stringify(s)).not.toContain('EARNED');
  });

  it('never shows a passed exam with no scope as a bare claim', () => {
    const exam = passed.ai.exam as NonNullable<AheadAnswer['ai']['exam']>;
    const s = aheadScene(input({ answer: { ...passed, ai: { ...passed.ai, exam: { ...exam, scope: null } } } }));
    expect(s.zone?.tags[1].text).toBe('passed its exam · scope not stated · 10 days, 100 moments');
  });

  it('takes a pass only when the exam agrees: a pass Nova cannot read the exam of is not shown as earned', () => {
    const unread: AheadAnswer = { ...passed, ai: { ...passed.ai, exam: null } };
    const hidden = aheadScene(input({ answer: unread }));
    noAi(hidden);
    expect(hidden.words[0]).toBe(AHEAD_WORDS.hiddenExamUnread);
    const shown = aheadScene(input({ answer: unread, prefs: { ...PREFS, unearned: true } }));
    expect(shown.zone?.tags[1]).toMatchObject({ text: AHEAD_WORDS.examUnread, fg: AHEAD_COLORS.notPassedFg });
    const exam = passed.ai.exam as NonNullable<AheadAnswer['ai']['exam']>;
    const disagree: AheadAnswer = { ...passed, ai: { ...passed.ai, exam: { ...exam, passed: false } } };
    expect(aheadScene(input({ answer: disagree })).fan).toBeNull();
  });

  it("counts the walls from the answer's close, not the chart's, when a wall edge lies between the two", () => {
    // The chart's close (4.58) is under the zone; the answer's close (4.62), where every path starts, is over it.
    const near = { id: 'near', lo: 4.6, hi: 4.605, label: '4.60 · double bottom', members: [{ kind: 'bottom' }] };
    const read = { ...READ, level_map: { ...READ?.level_map, intraday: [near] } } as AheadSceneInput['read'];
    const chart = candles().map((c) => ({ ...c, c: 4.58 }));
    const s = aheadScene(input({ answer: passed, read, candles: chart }));
    expect(s.walls?.above).toBeNull();
    expect(s.walls?.below?.zoneId).toBe('near');
    // With no AI view the chart's own close places them.
    const lines = aheadScene(input({ answer: passed, read, candles: chart, prefs: { ...PREFS, scope: 'lines' } }));
    expect(lines.walls?.above?.zoneId).toBe('near');
  });

  it('keeps the AI view off in the Lines scope and still draws the lines', () => {
    const s = aheadScene(input({ answer: passed, prefs: { ...PREFS, scope: 'lines' } }));
    noAi(s);
    expect(s.words[0]).toBe(AHEAD_WORDS.linesOnly);
    expect(s.lines.map((l) => l.kind)).toEqual(['support', 'resistance']);
    expect(s.meet).toMatchObject({ inZone: true, text: AHEAD_WORDS.meetAt(chartHhmm(ANCHOR + 300)) });
    expect(s.meet?.steps).toBeCloseTo(5);
    expect(s.meet?.p).toBeCloseTo(4.65);
  });

  it.each([
    ['not_set_up', answerNotSetUp, AHEAD_WORDS.notSetUp('NOVA_AHEAD_URL is not set')],
    ['offline', answerOffline, AHEAD_WORDS.offline(answerOffline.ai.reason)],
    ['warming', answerWarming, AHEAD_WORDS.warming],
    ['not_enough_bars', answerNotEnoughBars, AHEAD_WORDS.notEnoughBars(answerNotEnoughBars.ai.need, answerNotEnoughBars.ai.have)],
    ['quiet', answerQuiet, AHEAD_WORDS.quiet(4)],
    ['pending', answerPending, AHEAD_WORDS.pending],
    ['error', answerError, AHEAD_WORDS.error("the forecaster's answer is missing close")],
  ])('says why in the %s state and still draws the lines', (_state, raw, sentence) => {
    const s = aheadScene(input({ answer: raw as unknown as AheadAnswer, prefs: { ...PREFS, unearned: true } }));
    noAi(s);
    expect(s.words[0]).toBe(sentence);
    expect(s.lines).toHaveLength(2);
  });

  it('never draws over a real candle: a newer chart candle, or a chart behind the answer', () => {
    const newer = aheadScene(input({ answer: passed, candles: candles(240, ANCHOR + 60) }));
    noAi(newer);
    expect(newer.words[0]).toBe(AHEAD_WORDS.pending);
    expect(newer.anchorT).toBe(ANCHOR + 60);
    const behind = aheadScene(input({ answer: passed, candles: candles(240, ANCHOR - 60) }));
    noAi(behind);
    expect(behind.words[0]).toBe(AHEAD_WORDS.catchingUp);
  });

  it('tells the flat top as story paths over a soft cloud, their end labels its odds', () => {
    const s = aheadScene(input({ answer: passed, prefs: { ...PREFS, scope: 'flat_top' } }));
    const t = s.triggers?.flat_top;
    // No path in the cloud carries an outcome colour; the story paths do, from the fill on only.
    expect(s.cloud).toHaveLength(16);
    expect(s.story.length).toBeGreaterThan(0);
    for (const st of s.story) {
      expect(st.segments[0]).toMatchObject({ from: 0, color: AHEAD_COLORS.muted });
      expect(st.segments[st.segments.length - 1].to).toBe(15);
    }
    // The end labels replace the target-first / stop-first chips: the odds are said once.
    expect(s.chips.every((c) => c.role === 'story')).toBe(true);
    const target = s.story.find((st) => st.color === AHEAD_COLORS.target);
    if (target && t?.first) expect(target.label).toBe(AHEAD_WORDS.storyTarget(t.first.target));
    expect(s.legend.map((r) => r.text)).toContain(AHEAD_WORDS.legendStory(s.story.length));
    expect(s.hLines.map((h) => h.color)).toEqual([AHEAD_COLORS.trigger, AHEAD_COLORS.stop, AHEAD_COLORS.target]);
    expect(s.hLines[0].chip).toBe(AHEAD_WORDS.buyStop('4.70'));
    // The target sits on the next wall up (4.84 double top): its chip says so.
    expect(s.hLines[2].chip).toBe('target 4.84 · next wall');
    expect(s.chips.map((c) => c.short)).toEqual(s.story.map((st) => st.short));
    expect(s.chips.map((c) => c.story)).toEqual(s.story.map((_, i) => i));
    // Every length says what the share is of; only the full words carry "(forecast)" (the panel's card keeps it).
    for (const c of s.chips) {
      expect(c.text).toMatch(/^(✓ target first|✕ stop first|still open) · \d+% of fills \(forecast\)$|^never fills · \d+% of paths \(forecast\)$/);
      expect(c.short).toMatch(/^(✓ target first|✕ stop first|still open) · \d+% of fills$|^never fills · \d+% of paths$/);
      expect(c.tiny).toMatch(/^(✓ |✕ |open )\d+% of fills$|^never \d+% of paths$/);
    }
  });

  it("says why a strategy scope has nothing in play", () => {
    const s = aheadScene(input({ answer: passed, prefs: { ...PREFS, scope: 'first_pullback' } }));
    expect(s.hLines).toEqual([]);
    expect(s.words).toContain(AHEAD_WORDS.noLane('first pullback'));
  });

  it('keeps in view only what it draws', () => {
    const hidden = aheadScene(input());
    expect(hidden.keepInView).toEqual({ lo: 4.6, hi: 4.7 });
    const shown = aheadScene(input({ answer: passed }));
    expect(shown.keepInView?.lo).toBeCloseTo(4.5);
    expect(shown.keepInView?.hi).toBeCloseTo(4.84);
    // The story paths never stretch the scale: every path a dollar over the fan leaves it where the fan put it (the
    // renderer clips them and marks the edge with a caret).
    const paths = ready.ai.paths as NonNullable<AheadAnswer['ai']['paths']>;
    const high: AheadAnswer = { ...passed, ai: { ...passed.ai,
      paths: { ...paths, close: paths.close.map((p) => p.map((c) => c + 1)) } } };
    const far = aheadScene(input({ answer: high, symbol: 'FAR' }));
    expect(Math.max(...far.story.flatMap((st) => st.points))).toBeGreaterThan(5.5);
    expect(far.keepInView?.lo).toBeCloseTo(4.5);
    expect(far.keepInView?.hi).toBeCloseTo(4.84);
    // No room at the right edge draws no zone, so nothing of it stretches the price scale.
    expect(aheadScene(input({ answer: passed, roomOk: false })).keepInView).toBeNull();
  });

  it('says why when the API is missing, nothing was read yet, the replay is empty or there is no room', () => {
    const missing = aheadScene(input({ answer: null, fetchProblem: AHEAD_WORDS.apiMissing }));
    expect(missing.words[0]).toBe(AHEAD_WORDS.apiMissing);
    expect(missing.lines).toHaveLength(2);
    expect(aheadScene(input({ answer: null })).words[0]).toBe(AHEAD_WORDS.asking);
    expect(aheadScene(input({ candles: [], replayEmpty: true })).words).toEqual([AHEAD_WORDS.replayEmpty('XYZ')]);
    expect(aheadScene(input({ candles: [] })).words).toEqual([AHEAD_WORDS.noCandles]);
    expect(aheadScene(input({ roomOk: false })).words[0]).toBe(AHEAD_WORDS.noRoom);
    expect(aheadScene(input({ answer: passed })).fan).not.toBeNull();
    const none = aheadScene(input({ answer: passed, roomOk: false }));
    expect(none.zone).toBeNull();
    expect(none.fan).toBeNull();
    expect(none.cloud).toEqual([]);
    expect(none.story).toEqual([]);
    expect(none.lines).toEqual([]);
    expect(none.meet).toBeNull();
    expect(none.hLines).toEqual([]);
    expect(none.chips).toEqual([]);
    expect(none.ghostVolume).toBeNull();
    expect(none.macd).toBeNull();
    expect(none.keepInView).toBeNull();
    expect(none.legend).toEqual([]);
    const loading = aheadScene(input({ read: null }));
    expect(loading.words).toContain(AHEAD_WORDS.readLoading);
    expect(loading.lineRead).toBeNull();
  });

  it('shows the demo answer as Nova\'s lines only', () => {
    const s = aheadScene(input({ answer: sampleAhead('XYZ', 1792500065), prefs: { ...PREFS, unearned: true } }));
    noAi(s);
    expect(s.words[0]).toBe(AHEAD_WORDS.notSetUp(AHEAD_WORDS.demoReason));
    expect(s.lines).toHaveLength(2);
  });

  it('labels the zone, its now and its five-minute ticks from the anchor candle', () => {
    const s = aheadScene(input());
    expect(s.zone?.title).toBe(AHEAD_WORDS.zoneTitle);
    expect(s.zone?.nowText).toBe(`now ${chartHhmm(ANCHOR + 60)}`);
    expect(s.ticks.length).toBe(3);
    // In the desk's own axis words ("9:05 AM"), never a second clock style beside its labels.
    for (const tick of s.ticks) {
      expect(tick.text).toMatch(/^\d{1,2}:\d{2} (AM|PM)$/);
      expect(Number(tick.text.split(':')[1].slice(0, 2)) % 5).toBe(0);
    }
  });

  it('names a target off every wall plainly, and carries the real volumes for the panel', () => {
    const read = { ...READ, level_map: { ...READ?.level_map, intraday: [] } } as AheadSceneInput['read'];
    const s = aheadScene(input({ answer: passed, read, prefs: { ...PREFS, scope: 'flat_top' }, recentVolume: [1, 2] }));
    expect(s.hLines[2].chip).toBe(AHEAD_WORDS.targetAt('4.84'));
    expect(s.recentVolume).toEqual([1, 2]);
    expect(aheadScene(input({ answer: null })).examStatus).toBeNull();
  });

  it('draws no MACD fan without the MACD pane, and works the fan out once per minute', () => {
    expect(aheadScene(input({ answer: passed, macdOn: false })).macd).toBeNull();
    const a = aheadScene(input({ answer: passed }));
    const b = aheadScene(input({ answer: passed }));
    expect(b.macd).toBe(a.macd);
    expect(b.story).toBe(a.story);
    expect(b.triggers?.flat_top.first).toBe(a.triggers?.flat_top.first);
  });
});
