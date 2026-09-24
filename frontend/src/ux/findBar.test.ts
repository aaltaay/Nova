/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  FIND_BAR_TEXT,
  FIND_HIGHLIGHT,
  FIND_HIGHLIGHT_CURRENT,
  FIND_REFRESH_MS,
  FIND_TYPE_DEBOUNCE_MS,
  findCountLabel,
  installFindBar,
  isFindChord,
} from './findBar';

/** Stands in for the CSS Custom Highlight API jsdom lacks. */
class FakeHighlight {
  ranges: Range[];
  priority = 0;
  constructor(...ranges: Range[]) {
    this.ranges = ranges;
  }
}

let uninstall: () => void = () => undefined;
let registry: Map<string, FakeHighlight>;

const bar = () => document.querySelector<HTMLElement>('.find-bar')!;
const input = () => bar().querySelector<HTMLInputElement>('input')!;
const count = () => bar().querySelector('.find-bar__count')!.textContent;
const btn = (act: string) => bar().querySelector<HTMLButtonElement>(`.find-bar__btn--${act}`)!;
const current = () => registry.get(FIND_HIGHLIGHT_CURRENT)?.ranges[0];

function pressCtrlF(target: EventTarget = document.body): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key: 'f', code: 'KeyF', ctrlKey: true, bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
}

function type(text: string) {
  input().value = text;
  input().dispatchEvent(new Event('input', { bubbles: true }));
  vi.advanceTimersByTime(FIND_TYPE_DEBOUNCE_MS);
}

function key(name: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true, ...init });
  input().dispatchEvent(event);
  return event;
}

beforeEach(() => {
  vi.useFakeTimers();
  registry = new Map();
  vi.stubGlobal('CSS', { highlights: registry });
  vi.stubGlobal('Highlight', FakeHighlight);
  document.body.innerHTML = `
    <main>
      <div class="row"><span>GCTK</span> 4.13</div>
      <div class="row"><span>PFSA</span> 1.80</div>
      <div class="row"><span>gctk</span> <button id="ticket">Buy GCTK</button></div>
    </main>`;
  uninstall = installFindBar(document);
});

afterEach(() => {
  uninstall();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('the find bar', () => {
  it('opens on Ctrl+F, counts the page, and marks every match and the current one', () => {
    expect(bar().hidden).toBe(true);
    const event = pressCtrlF();
    expect(event.defaultPrevented).toBe(true);   // the browser's own find stays shut
    expect(bar().hidden).toBe(false);
    expect(document.activeElement).toBe(input());
    type('gctk');
    expect(count()).toBe('1 of 3');
    expect(registry.get(FIND_HIGHLIGHT)?.ranges.map(String)).toEqual(['GCTK', 'gctk', 'GCTK']);
    expect(String(current())).toBe('GCTK');
    expect(registry.get(FIND_HIGHLIGHT_CURRENT)?.priority).toBe(1);
  });

  it('moves with Enter and Shift+Enter and the arrows, wrapping at both ends', () => {
    pressCtrlF();
    type('gctk');
    key('Enter');
    expect(count()).toBe('2 of 3');
    key('Enter');
    key('Enter');
    expect(count()).toBe('1 of 3');
    key('Enter', { shiftKey: true });
    expect(count()).toBe('3 of 3');
    btn('prev').click();
    expect(count()).toBe('2 of 3');
    btn('next').click();
    expect(count()).toBe('3 of 3');
    expect(document.activeElement).toBe(input());
  });

  it('Enter before the typing pause searches first instead of skipping the first match', () => {
    pressCtrlF();
    input().value = 'pfsa';
    input().dispatchEvent(new Event('input', { bubbles: true }));
    key('Enter');
    expect(count()).toBe('1 of 1');
  });

  it('says so when nothing matches, and the arrows say why they are locked', () => {
    pressCtrlF();
    expect(btn('next').disabled).toBe(true);
    expect(btn('next').getAttribute('data-why')).toBe(FIND_BAR_TEXT.whyEmpty);
    type('zzzz');
    expect(count()).toBe('No matches');
    expect(btn('prev').getAttribute('data-why')).toBe(FIND_BAR_TEXT.whyNone);
    type('pfsa');
    expect(btn('prev').disabled).toBe(false);
    expect(btn('prev').hasAttribute('data-why')).toBe(false);
  });

  it('Esc closes it, clears the marks and gives focus back', () => {
    const ticket = document.getElementById('ticket')!;
    ticket.focus();
    pressCtrlF(ticket);
    type('gctk');
    const esc = key('Escape');
    expect(esc.defaultPrevented).toBe(true);
    expect(bar().hidden).toBe(true);
    expect(registry.size).toBe(0);
    expect(document.activeElement).toBe(ticket);
  });

  it('keeps every key typed in the box away from the rest of the page', () => {
    pressCtrlF();
    const heard = vi.fn();
    window.addEventListener('keydown', heard);
    key('b');
    key('Enter');
    key('Escape');
    window.removeEventListener('keydown', heard);
    expect(heard).not.toHaveBeenCalled();
  });

  it('leaves Ctrl+F to a trading hotkey that already handled it', () => {
    const hotkey = (event: KeyboardEvent) => {
      if (isFindChord(event)) event.preventDefault();
    };
    window.addEventListener('keydown', hotkey, true);
    pressCtrlF();
    window.removeEventListener('keydown', hotkey, true);
    expect(bar().hidden).toBe(true);
  });

  it('Ctrl+F while open selects the query to type over it', () => {
    pressCtrlF();
    type('gctk');
    input().setSelectionRange(4, 4);
    pressCtrlF(input());
    expect(input().selectionStart).toBe(0);
    expect(input().selectionEnd).toBe(4);
  });

  it('counts again as the page changes, keeping the current match', () => {
    pressCtrlF();
    type('gctk');
    key('Enter');
    expect(String(current())).toBe('gctk');
    const row = document.createElement('div');
    row.innerHTML = '<span>GCTK</span> 4.20';
    document.querySelector('main')!.prepend(row);
    return Promise.resolve().then(() => {   // MutationObserver delivers on a microtask
      vi.advanceTimersByTime(FIND_REFRESH_MS);
      expect(count()).toBe('3 of 4');
      expect(String(current())).toBe('gctk');
    });
  });

  it('installs once per window', () => {
    expect(installFindBar(document)).toBe(uninstall);
    expect(document.querySelectorAll('.find-bar')).toHaveLength(1);
  });
});

describe('findCountLabel', () => {
  it('reads like a browser count, says when there were more, and says nothing before a query', () => {
    expect(findCountLabel(0, 12, false, true)).toBe('1 of 12');
    expect(findCountLabel(4, 1000, true, true)).toBe('5 of 1,000+');
    expect(findCountLabel(-1, 0, false, true)).toBe('No matches');
    expect(findCountLabel(-1, 0, false, false)).toBe('');
  });
});

describe('isFindChord', () => {
  it('is Ctrl+F (or Cmd+F) and nothing else', () => {
    const k = (init: KeyboardEventInit) => new KeyboardEvent('keydown', init);
    expect(isFindChord(k({ key: 'f', ctrlKey: true }))).toBe(true);
    expect(isFindChord(k({ key: 'F', metaKey: true }))).toBe(true);
    expect(isFindChord(k({ key: 'а', code: 'KeyF', ctrlKey: true }))).toBe(true);   // a Cyrillic layout
    expect(isFindChord(k({ key: 'f' }))).toBe(false);
    expect(isFindChord(k({ key: 'F', ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(isFindChord(k({ key: 'f', ctrlKey: true, altKey: true }))).toBe(false);
  });
});
