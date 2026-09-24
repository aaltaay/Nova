/**
 * @vitest-environment jsdom
 *
 * The desk-wide "why is this locked" tip: a locked control's reason shows on
 * hover and at once on a refused press; an enabled control stays quiet.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installWhyTip, lockedTarget, whyProps, WHY_TIP_HOVER_MS, WHY_TIP_PRESS_HOLD_MS } from './whyTip';

function tip(): HTMLElement {
  const el = document.getElementById('nova-why-tip');
  if (!el) throw new Error('tip not installed');
  return el;
}

function fire(type: string, target: Element, relatedTarget: Element | null = null): MouseEvent {
  const ev = new MouseEvent(type, { bubbles: true, cancelable: true, composed: true, relatedTarget });
  target.dispatchEvent(ev);
  return ev;
}

describe('whyTip', () => {
  let uninstall: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      <div id="bar">
        <button id="locked" disabled data-why="No scanner yet -- it cannot play">Gap and Go</button>
        <button id="open" data-why="stale reason">Enabled</button>
        <label id="pick" aria-disabled="true" data-why="Pick a setup that has a scanner"><span id="inner">Red to green</span></label>
        <button id="aria" aria-disabled="true" data-why="Unlock the padlock first">Strategy</button>
        <span id="plain">plain</span>
        <label id="eh-label"><input id="eh" type="checkbox" disabled data-why="Sending the order"> Extended Hours</label>
      </div>`;
    uninstall = installWhyTip(document);
  });

  afterEach(() => {
    uninstall();
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('shows a locked control reason after the hover delay and hides it on leave', () => {
    const locked = document.getElementById('locked')!;
    fire('pointerover', locked);
    expect(tip().hidden).toBe(true);
    vi.advanceTimersByTime(WHY_TIP_HOVER_MS);
    expect(tip().hidden).toBe(false);
    expect(tip().textContent).toBe('No scanner yet -- it cannot play');
    fire('pointerout', locked, document.getElementById('plain'));
    expect(tip().hidden).toBe(true);
  });

  it('stays quiet on an enabled control, even with a stale reason on it', () => {
    fire('pointerover', document.getElementById('open')!);
    vi.advanceTimersByTime(WHY_TIP_HOVER_MS * 2);
    expect(tip().hidden).toBe(true);
  });

  it('answers a refused press at once and holds it after the pointer moves on', () => {
    const locked = document.getElementById('locked')!;
    fire('pointerdown', locked);
    expect(tip().hidden).toBe(false);
    expect(tip().classList.contains('why-tip--pressed')).toBe(true);
    fire('pointerout', locked, document.getElementById('plain'));
    expect(tip().hidden).toBe(false);
    vi.advanceTimersByTime(WHY_TIP_PRESS_HOLD_MS);
    expect(tip().hidden).toBe(true);
  });

  it('reads the reason from an aria-disabled wrapper when a child is hovered', () => {
    fire('pointerover', document.getElementById('inner')!);
    vi.advanceTimersByTime(WHY_TIP_HOVER_MS);
    expect(tip().textContent).toBe('Pick a setup that has a scanner');
  });

  it('swallows the click on an aria-disabled control and says why', () => {
    const aria = document.getElementById('aria')!;
    const onClick = vi.fn();
    aria.addEventListener('click', onClick);
    const ev = fire('click', aria);
    expect(onClick).not.toHaveBeenCalled();
    expect(ev.defaultPrevented).toBe(true);
    expect(tip().textContent).toBe('Unlock the padlock first');
  });

  it('switches straight to the next locked control once one is showing', () => {
    fire('pointerover', document.getElementById('locked')!);
    vi.advanceTimersByTime(WHY_TIP_HOVER_MS);
    fire('pointerover', document.getElementById('aria')!);
    expect(tip().textContent).toBe('Unlock the padlock first');
  });

  it('explains a locked checkbox from its label text too', () => {
    fire('pointerover', document.getElementById('eh-label')!);
    vi.advanceTimersByTime(WHY_TIP_HOVER_MS);
    expect(tip().textContent).toBe('Sending the order');
  });

  it('Escape hides it', () => {
    fire('pointerdown', document.getElementById('locked')!);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(tip().hidden).toBe(true);
  });

  it('is installed once per document', () => {
    expect(installWhyTip(document)).toBe(uninstall);
    expect(document.querySelectorAll('#nova-why-tip')).toHaveLength(1);
  });

  it('lockedTarget and whyProps', () => {
    expect(lockedTarget(document.getElementById('open'))).toBeNull();
    expect(lockedTarget(document.getElementById('plain'))).toBeNull();
    expect(lockedTarget(document.getElementById('locked'))?.id).toBe('locked');
    expect(whyProps(true, ' Not connected ')).toEqual({ 'data-why': 'Not connected' });
    expect(whyProps(false, 'Not connected')).toEqual({});
    expect(whyProps(true, '')).toEqual({});
  });
});
