/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import answerReady from './__fixtures__/answer_ready.json';
import {
  aheadHeldOf,
  clearAhead,
  closeAheadSheet,
  openAheadSheet,
  publishAhead,
  resetAheadStoreForTesting,
  useAheadAnswerOf,
  useAheadSheetOpen,
} from './aheadStore';
import type { AheadAnswer } from './aheadTypes';

const ready = answerReady as unknown as AheadAnswer;

describe("Ahead's per-symbol store", () => {
  beforeEach(() => resetAheadStoreForTesting());

  it('holds one answer per symbol, whatever the case it is asked in', () => {
    const { result } = renderHook(() => useAheadAnswerOf('xyz'));
    expect(result.current).toBeNull();
    act(() => publishAhead('XYZ', { answer: ready, problem: null }));
    expect(result.current).toBe(ready);
    expect(aheadHeldOf('ABC').answer).toBeNull();
    act(() => clearAhead('Xyz'));
    expect(result.current).toBeNull();
  });

  it('keeps the words of a failed read', () => {
    publishAhead('XYZ', { answer: null, problem: 'no API' });
    expect(aheadHeldOf('XYZ')).toEqual({ answer: null, problem: 'no API' });
  });

  it('opens and closes the panel per symbol', () => {
    const { result } = renderHook(() => useAheadSheetOpen('XYZ'));
    expect(result.current).toBe(false);
    act(() => openAheadSheet('xyz'));
    expect(result.current).toBe(true);
    act(() => closeAheadSheet('XYZ'));
    expect(result.current).toBe(false);
  });
});
