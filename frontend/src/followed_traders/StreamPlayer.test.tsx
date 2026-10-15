/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setDeskMuted } from '../sound';
import { StreamPlayer } from './StreamPlayer';

describe('StreamPlayer under the header mute', () => {
  beforeEach(() => {
    localStorage.clear();
    setDeskMuted(false);
  });
  afterEach(() => {
    cleanup();
    setDeskMuted(false);
  });

  it('the header mute mutes the stream and holds its sound button, saying why', () => {
    render(<StreamPlayer videoId="abcdefghijk" title="Live" offAir={null} />);
    const btn = screen.getByTestId('ft-stream-sound');
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-pressed')).toBe('true'); // sound on
    act(() => setDeskMuted(true));
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    expect(btn.getAttribute('data-why')).toMatch(/header mute is on/);
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-pressed')).toBe('false'); // held: still muted
    act(() => setDeskMuted(false));
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    expect(btn.getAttribute('aria-pressed')).toBe('false'); // back on, the stream stays muted until asked
  });
});
