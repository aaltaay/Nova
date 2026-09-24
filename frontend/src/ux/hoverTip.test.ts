/**
 * @vitest-environment jsdom
 *
 * The desk-wide "what does this mean" tip (ADR 031; operator ask 2026-09-24: "we
 * are going to need lots of hovers, explaining in detail what each means"): an
 * element's `data-tip` shows on hover and on focus, as text, and a locked
 * control's `data-why` answers instead -- the two never stack.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOVER_TIP_DELAY_MS, HOVER_TIP_REFRESH_MS, installHoverTip, tipProps, tipTarget } from './hoverTip';

function tip(): HTMLElement {
  const el = document.getElementById('nova-hover-tip');
  if (!el) throw new Error('tip not installed');
  return el;
}

function fire(type: string, target: Element, relatedTarget: Element | null = null): void {
  target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, composed: true, relatedTarget }));
}

describe('hoverTip', () => {
  let uninstall: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      <div>
        <span id="near" data-tip="Price is a few cents under the trigger.&#10;Now: 0.03 under" data-tip-title="Near · First pullback"><b id="inner">Near</b></span>
        <span id="go" data-tip="GO: green prints at the ask">GO</span>
        <button id="locked" disabled data-why="Only the chosen setup can be at Strategy" data-tip="Strategy: the bot trades it">Strategy</button>
        <span id="html" data-tip="<img src=x onerror=alert(1)> plain">x</span>
        <button id="focusable" data-tip="Eyes: proposes on near + go">Eyes</button>
        <span id="plain">plain</span>
      </div>`;
    uninstall = installHoverTip(document);
  });

  afterEach(() => {
    uninstall();
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('shows the tip with its heading after the hover delay, and hides it on leave', () => {
    fire('pointerover', document.getElementById('inner')!);
    expect(tip().hidden).toBe(true);
    vi.advanceTimersByTime(HOVER_TIP_DELAY_MS);
    expect(tip().hidden).toBe(false);
    expect(tip().querySelector('.hover-tip__title')?.textContent).toBe('Near · First pullback');
    expect(tip().querySelector('.hover-tip__body')?.textContent).toBe('Price is a few cents under the trigger.\nNow: 0.03 under');
    fire('pointerout', document.getElementById('near')!, document.getElementById('plain'));
    expect(tip().hidden).toBe(true);
  });

  it('answers at once when the pointer moves from one explained chip to the next', () => {
    fire('pointerover', document.getElementById('near')!);
    vi.advanceTimersByTime(HOVER_TIP_DELAY_MS);
    fire('pointerout', document.getElementById('near')!, document.getElementById('go'));
    expect(tip().hidden).toBe(false);
    expect(tip().querySelector('.hover-tip__body')?.textContent).toBe('GO: green prints at the ask');
    expect((tip().querySelector('.hover-tip__title') as HTMLElement).hidden).toBe(true);
  });

  it('leaves a locked control to the why-tip, so the two never stack', () => {
    expect(tipTarget(document.getElementById('locked'))).toBeNull();
    fire('pointerover', document.getElementById('locked')!);
    vi.advanceTimersByTime(HOVER_TIP_DELAY_MS * 2);
    expect(tip().hidden).toBe(true);
  });

  it('writes text, never HTML', () => {
    fire('pointerover', document.getElementById('html')!);
    vi.advanceTimersByTime(HOVER_TIP_DELAY_MS);
    expect(tip().querySelector('img')).toBeNull();
    expect(tip().querySelector('.hover-tip__body')?.textContent).toBe('<img src=x onerror=alert(1)> plain');
  });

  it('explains a focused control too, and Escape puts it away', () => {
    document.getElementById('focusable')!.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    expect(tip().hidden).toBe(false);
    expect(tip().textContent).toContain('Eyes: proposes on near + go');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(tip().hidden).toBe(true);
  });

  it('keeps a live number current while the tip is up', () => {
    const go = document.getElementById('go')!;
    fire('pointerover', go);
    vi.advanceTimersByTime(HOVER_TIP_DELAY_MS);
    go.setAttribute('data-tip', 'GO: 2 cents under the trigger now');
    vi.advanceTimersByTime(HOVER_TIP_REFRESH_MS);
    expect(tip().querySelector('.hover-tip__body')?.textContent).toBe('GO: 2 cents under the trigger now');
    go.remove();
    vi.advanceTimersByTime(HOVER_TIP_REFRESH_MS);
    expect(tip().hidden).toBe(true);
  });

  it('steps aside when the control it explains locks under the pointer', () => {
    const eyes = document.getElementById('focusable')!;
    fire('pointerover', eyes);
    vi.advanceTimersByTime(HOVER_TIP_DELAY_MS);
    expect(tip().hidden).toBe(false);
    eyes.setAttribute('disabled', '');
    eyes.setAttribute('data-why', 'Saving the last change');
    vi.advanceTimersByTime(HOVER_TIP_REFRESH_MS);
    expect(tip().hidden).toBe(true);
  });

  it('builds its attributes from text, and none from an empty text', () => {
    expect(tipProps('  What it means  ', 'Near')).toEqual({ 'data-tip': 'What it means', 'data-tip-title': 'Near' });
    expect(tipProps('What it means')).toEqual({ 'data-tip': 'What it means' });
    expect(tipProps('   ', 'Near')).toEqual({});
    expect(tipProps(null)).toEqual({});
  });

  it('installs once per document', () => {
    expect(installHoverTip(document)).toBe(uninstall);
    expect(document.querySelectorAll('#nova-hover-tip')).toHaveLength(1);
  });
});
