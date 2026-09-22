/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { HoldToStopButton } from './HoldToStopButton';

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

function mount(onConfirm = vi.fn()) {
  render(<HoldToStopButton label="Hold to stop recording GRML" holdMs={1000} onConfirm={onConfirm} testId="hold" />);
  return { button: screen.getByTestId('hold'), onConfirm };
}

it('fires only after the whole hold', () => {
  const { button, onConfirm } = mount();
  fireEvent.pointerDown(button, { button: 0 });
  act(() => { vi.advanceTimersByTime(900); });
  expect(onConfirm).not.toHaveBeenCalled();
  act(() => { vi.advanceTimersByTime(150); });
  expect(onConfirm).toHaveBeenCalledTimes(1);
});

it('a click, or letting go early, keeps recording', () => {
  const { button, onConfirm } = mount();
  fireEvent.click(button);
  fireEvent.pointerDown(button, { button: 0 });
  act(() => { vi.advanceTimersByTime(600); });
  fireEvent.pointerUp(button);
  act(() => { vi.advanceTimersByTime(1000); });
  expect(onConfirm).not.toHaveBeenCalled();
  fireEvent.pointerDown(button, { button: 0 });
  act(() => { vi.advanceTimersByTime(600); });
  fireEvent.pointerLeave(button);
  act(() => { vi.advanceTimersByTime(1000); });
  expect(onConfirm).not.toHaveBeenCalled();
});

it('the fill shows the hold and empties on release', () => {
  const { button } = mount();
  const fill = button.querySelector('.hold-to-stop__fill') as HTMLElement;
  fireEvent.pointerDown(button, { button: 0 });
  act(() => { vi.advanceTimersByTime(500); });
  expect(parseFloat(fill.style.width)).toBeGreaterThan(40);
  fireEvent.pointerUp(button);
  expect(parseFloat(fill.style.width)).toBe(0);
});

it('a held key works like a held pointer', () => {
  const { button, onConfirm } = mount();
  fireEvent.keyDown(button, { key: 'Enter' });
  act(() => { vi.advanceTimersByTime(500); });
  fireEvent.keyUp(button, { key: 'Enter' });
  act(() => { vi.advanceTimersByTime(1000); });
  expect(onConfirm).not.toHaveBeenCalled();
  fireEvent.keyDown(button, { key: ' ' });
  act(() => { vi.advanceTimersByTime(1050); });
  expect(onConfirm).toHaveBeenCalledTimes(1);
});
