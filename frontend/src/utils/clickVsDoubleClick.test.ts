import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createClickVsDoubleClick } from './clickVsDoubleClick';

describe('createClickVsDoubleClick', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fires onSingle after the delay when clicked once', () => {
    const onSingle = vi.fn();
    const onDouble = vi.fn();
    const { handleClick } = createClickVsDoubleClick(onSingle, onDouble, 280);

    handleClick();
    expect(onSingle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(279);
    expect(onSingle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onSingle).toHaveBeenCalledOnce();
    expect(onDouble).not.toHaveBeenCalled();
  });

  it('fires onDouble and suppresses onSingle when clicked twice within the delay', () => {
    const onSingle = vi.fn();
    const onDouble = vi.fn();
    const { handleClick } = createClickVsDoubleClick(onSingle, onDouble, 280);

    handleClick();
    vi.advanceTimersByTime(100);
    handleClick();
    expect(onDouble).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(500);
    expect(onSingle).not.toHaveBeenCalled();
  });

  it('cancel prevents a pending single click', () => {
    const onSingle = vi.fn();
    const onDouble = vi.fn();
    const { handleClick, cancel } = createClickVsDoubleClick(onSingle, onDouble, 280);

    handleClick();
    cancel();
    vi.advanceTimersByTime(500);
    expect(onSingle).not.toHaveBeenCalled();
    expect(onDouble).not.toHaveBeenCalled();
  });
});
