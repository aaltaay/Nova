/** @vitest-environment jsdom */
/**
 * The brain's Level 2 frame on the Trader (ADR 072 decision 10): purple, tagged "The brain's line · you share it",
 * while the pane's stock is the brain's lane's and its Level 2 is up -- and never over Claude's frame.
 */
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BrainLineFrame } from './BrainLineFrame';
import { BRAIN_WATCHING, brainStatus } from './brainSeatFixtures';
import { resetBrainSeatForTests, setBrainSeatForTests } from './brainSeatStore';

/** Claude's seat as its barrel hands it: only the line matters here. */
const claude = vi.hoisted(() => ({ line: null as null | { symbol: string | null; depth: boolean } }));
vi.mock('../claude_seat', () => ({
  useClaudeSeat: () => ({ status: claude.line ? { line: claude.line } : null, error: null }),
}));

beforeEach(() => {
  claude.line = null;
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
  resetBrainSeatForTests();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetBrainSeatForTests();
});

function framed(symbol: string | null) {
  render(<BrainLineFrame symbol={symbol}><div data-testid="columns" /></BrainLineFrame>);
}

describe("the brain's line frame", () => {
  it('frames Level 2 and Time & Sales while the pane is on the brain\'s lane stock', () => {
    framed('ssii');
    act(() => setBrainSeatForTests(brainStatus(BRAIN_WATCHING)));
    const frame = screen.getByTestId('brain-line-frame');
    expect(frame.textContent).toBe("The brain's line · you share it");
    expect(frame.className).toBe('brain-line-frame');
    expect(frame.contains(screen.getByTestId('columns'))).toBe(true);
  });

  it('is no box on another stock, with no lane stock, before its Level 2 is up, or in a replay', () => {
    framed('XLAB');
    act(() => setBrainSeatForTests(brainStatus(BRAIN_WATCHING)));
    expect(screen.queryByTestId('brain-line-frame')).toBeNull();
    expect(screen.getByTestId('columns').parentElement!.className).toBe('brain-line-frame brain-line-frame--off');
    act(() => setBrainSeatForTests(brainStatus({ ...BRAIN_WATCHING, lane: { symbol: 'XLAB', depth: false, tape: false } })));
    expect(screen.queryByTestId('brain-line-frame')).toBeNull();
    cleanup();
    framed(null);
    act(() => setBrainSeatForTests(brainStatus(BRAIN_WATCHING)));
    expect(screen.queryByTestId('brain-line-frame')).toBeNull();
  });

  it('never remounts what it wraps when the frame comes or goes', () => {
    framed('SSII');
    const before = screen.getByTestId('columns');
    act(() => setBrainSeatForTests(brainStatus(BRAIN_WATCHING)));
    expect(screen.getByTestId('brain-line-frame')).toBeTruthy();
    expect(screen.getByTestId('columns')).toBe(before);
  });

  it("yields to Claude's frame on a stock both lanes are on", () => {
    claude.line = { symbol: 'SSII', depth: true };
    framed('SSII');
    act(() => setBrainSeatForTests(brainStatus(BRAIN_WATCHING)));
    expect(screen.queryByTestId('brain-line-frame')).toBeNull();
  });

  it("keeps its frame while Claude's lane is on another stock, or its Level 2 is not up", () => {
    claude.line = { symbol: 'RUNR', depth: true };
    framed('SSII');
    act(() => setBrainSeatForTests(brainStatus(BRAIN_WATCHING)));
    expect(screen.getByTestId('brain-line-frame')).toBeTruthy();
    cleanup();
    claude.line = { symbol: 'SSII', depth: false };
    framed('SSII');
    act(() => setBrainSeatForTests(brainStatus(BRAIN_WATCHING)));
    expect(screen.getByTestId('brain-line-frame')).toBeTruthy();
  });
});
