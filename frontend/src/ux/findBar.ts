/**
 * Find on this page -- Ctrl+F in every Nova window (operator ask 2026-09-24:
 * "can we also do like CTRL+F so maybe we can search on anything in that
 * screen instead of looking everywhere?"). The desktop app shows no find bar
 * of its own (Electron has none), so this module owns the one every window
 * gets, in the desktop app and the browser alike:
 *
 * - Ctrl+F opens it, or selects its text when it is open. Typing searches the
 *   page as it is now (`ux/findText.ts`: case ignored, only what is shown);
 *   every match is marked and the current one is brighter. The first current
 *   match is one already on screen when there is one, so typing never jumps
 *   away from what the operator is looking at.
 * - Enter / Shift+Enter, or the arrows, move to the next / previous match and
 *   bring it into view; Esc or x closes the bar and gives focus back.
 * - The desk keeps moving: while a search is up and the page changes, it is
 *   searched again at most every `FIND_REFRESH_MS`, keeping the current match
 *   where it can and never scrolling on its own.
 * - Text is found only where it is drawn as text: a chart is a canvas, and a
 *   long list that draws only its visible rows finds only those.
 * - A trading hotkey bound to Ctrl+F keeps it: the hotkey dispatcher listens
 *   on the window before this bar (document, capture) and marks a key it
 *   handled, and this bar leaves a handled key alone.
 * - Keys typed in the box stay in it: the trading hotkeys never act on a key
 *   typed into a text field (`hooks/hotkeyUtils.isEditableTarget`), and the
 *   box stops every key it gets from reaching the rest of the page.
 *
 * Owner: this module. `installFindBar` runs once per window from `main.tsx`,
 * before the app's constants load, so it imports none of them.
 */
import './findBar.css';
import { FIND_BAR_ATTR, findMatches, type FindMatch } from './findText';

/** More matches than this counts as "1,000+". */
export const FIND_MAX_MATCHES = 1000;
/** Typing searches once it pauses this long. */
export const FIND_TYPE_DEBOUNCE_MS = 120;
/** While a search is up, a changed page is searched again at most this often. */
export const FIND_REFRESH_MS = 500;
/** The CSS highlight names (`findBar.css` draws them). */
export const FIND_HIGHLIGHT = 'nova-find';
export const FIND_HIGHLIGHT_CURRENT = 'nova-find-current';
/** The chord, as the shortcuts menu shows it. */
export const FIND_CHORD_LABEL = 'Ctrl+F';

export const FIND_BAR_TEXT = {
  label: 'Find on this page',
  prev: 'Previous match (Shift+Enter)',
  next: 'Next match (Enter)',
  close: 'Close (Esc)',
  none: 'No matches',
  keys: 'Enter next · Shift+Enter previous · Esc closes',
  whyEmpty: 'Type something to find first',
  whyNone: 'Nothing on this page matches -- nothing to move between',
} as const;

const OBSERVE: MutationObserverInit = {
  subtree: true,
  childList: true,
  characterData: true,
  attributes: true,
  attributeFilter: ['class', 'style', 'hidden'],
};

type FindBarDocument = Document & { __novaFindBar?: () => void };

/** Ctrl+F (Cmd+F on a Mac) with no other modifier, on any keyboard layout. */
export function isFindChord(event: KeyboardEvent): boolean {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return false;
  return event.key === 'f' || event.key === 'F' || event.code === 'KeyF';
}

/** "3 of 12", "3 of 1,000+", "No matches" -- or nothing before a query. */
export function findCountLabel(current: number, total: number, capped: boolean, hasQuery: boolean): string {
  if (!hasQuery) return '';
  if (total === 0) return FIND_BAR_TEXT.none;
  return `${current + 1} of ${total.toLocaleString('en-US')}${capped ? '+' : ''}`;
}

function highlights(): HighlightRegistry | null {
  const css = (globalThis as { CSS?: { highlights?: HighlightRegistry } }).CSS;
  return css?.highlights ?? null;
}

function highlightType(): typeof Highlight | null {
  const ctor = (globalThis as { Highlight?: typeof Highlight }).Highlight;
  return typeof ctor === 'function' ? ctor : null;
}

/** Install the find bar on `doc` (idempotent per document). Returns the uninstall (tests). */
export function installFindBar(doc: Document = document): () => void {
  const view = doc.defaultView;
  if (!view || !doc.body) return () => undefined;
  const existing = (doc as FindBarDocument).__novaFindBar;
  if (existing) return existing;

  const bar = doc.createElement('div');
  bar.className = 'find-bar';
  bar.setAttribute(FIND_BAR_ATTR, '');
  bar.setAttribute('role', 'search');
  bar.setAttribute('aria-label', FIND_BAR_TEXT.label);
  bar.hidden = true;
  const input = doc.createElement('input');
  input.type = 'text';
  input.className = 'find-bar__input';
  input.placeholder = FIND_BAR_TEXT.label;
  input.setAttribute('aria-label', FIND_BAR_TEXT.label);
  input.spellcheck = false;
  input.autocomplete = 'off';
  const count = doc.createElement('span');
  count.className = 'find-bar__count';
  count.setAttribute('aria-live', 'polite');
  const button = (act: string, glyph: string, label: string): HTMLButtonElement => {
    const b = doc.createElement('button');
    b.type = 'button';
    b.className = `find-bar__btn find-bar__btn--${act}`;
    b.textContent = glyph;
    b.setAttribute('aria-label', label);
    b.setAttribute('data-tip', label);
    return b;
  };
  const prev = button('prev', '↑', FIND_BAR_TEXT.prev);
  const next = button('next', '↓', FIND_BAR_TEXT.next);
  const close = button('close', '×', FIND_BAR_TEXT.close);
  bar.append(input, count, prev, next, close);
  doc.body.appendChild(bar);

  let query = '';
  let matches: FindMatch[] = [];
  let capped = false;
  let current = -1;
  let returnFocus: HTMLElement | null = null;
  let typeTimer: number | undefined;
  let refreshTimer: number | undefined;

  const hasQuery = () => query.trim().length > 0;

  const render = () => {
    const label = findCountLabel(current, matches.length, capped, hasQuery());
    if (count.textContent !== label) count.textContent = label;
    count.classList.toggle('find-bar__count--none', hasQuery() && matches.length === 0);
    const why = hasQuery() ? FIND_BAR_TEXT.whyNone : FIND_BAR_TEXT.whyEmpty;
    for (const b of [prev, next]) {
      const locked = matches.length === 0;
      if (b.disabled !== locked) b.disabled = locked;
      if (locked) {
        if (b.getAttribute('data-why') !== why) b.setAttribute('data-why', why);
      } else if (b.hasAttribute('data-why')) {
        b.removeAttribute('data-why');
      }
    }
  };

  const unpaint = () => {
    const registry = highlights();
    registry?.delete(FIND_HIGHLIGHT);
    registry?.delete(FIND_HIGHLIGHT_CURRENT);
  };

  const paint = () => {
    const registry = highlights();
    const Mark = highlightType();
    if (!registry || !Mark) return;
    if (matches.length === 0) {
      unpaint();
      return;
    }
    registry.set(FIND_HIGHLIGHT, new Mark(...matches.map((m) => m.range)));
    const now = matches[current];
    if (!now) {
      registry.delete(FIND_HIGHLIGHT_CURRENT);
      return;
    }
    const mark = new Mark(now.range);
    mark.priority = 1;
    registry.set(FIND_HIGHLIGHT_CURRENT, mark);
  };

  /** Bring the current match into view (only on the operator's own search or move). */
  const reveal = () => {
    const el = matches[current]?.node.parentElement;
    el?.scrollIntoView?.({ block: 'center', inline: 'nearest' });
  };

  /** The first match already on screen, else the first one. */
  const firstOnScreen = (): number => {
    const height = view.innerHeight;
    for (let i = 0; i < matches.length; i += 1) {
      const rect = matches[i].range.getBoundingClientRect?.();
      if (rect && (rect.width > 0 || rect.height > 0) && rect.bottom > 0 && rect.top < height) return i;
    }
    return 0;
  };

  const clearTimers = () => {
    if (typeTimer !== undefined) view.clearTimeout(typeTimer);
    if (refreshTimer !== undefined) view.clearTimeout(refreshTimer);
    typeTimer = undefined;
    refreshTimer = undefined;
  };

  const run = () => findMatches(doc.body, query, FIND_MAX_MATCHES);

  /** The operator's new query: search, pick a match on screen, show it. */
  const search = () => {
    clearTimers();
    query = input.value;
    ({ matches, capped } = run());
    current = matches.length ? firstOnScreen() : -1;
    paint();
    render();
    reveal();
  };

  /** The page changed under a search: search again and keep the current match where it can. */
  const refresh = () => {
    refreshTimer = undefined;
    if (bar.hidden || !hasQuery()) return;
    const kept = matches[current];
    ({ matches, capped } = run());
    let index = kept ? matches.findIndex((m) => m.node === kept.node && m.offset === kept.offset) : -1;
    if (index < 0) index = matches.length ? Math.min(Math.max(current, 0), matches.length - 1) : -1;
    current = index;
    paint();
    render();
  };

  /** A search still owed (typed, or the page changed): run it now, before a move. */
  const settle = (): boolean => {
    if (typeTimer !== undefined) {
      search();
      return true;
    }
    if (refreshTimer !== undefined) {
      view.clearTimeout(refreshTimer);
      refresh();
    }
    return false;
  };

  const move = (step: 1 | -1) => {
    if (matches.length === 0) return;
    current = current < 0
      ? (step > 0 ? 0 : matches.length - 1)
      : (current + step + matches.length) % matches.length;
    paint();
    render();
    reveal();
  };

  const observer = typeof view.MutationObserver === 'function'
    ? new view.MutationObserver((records) => {
      if (bar.hidden || !hasQuery() || refreshTimer !== undefined) return;
      if (records.every((r) => bar.contains(r.target))) return;   // only the bar's own count changed
      refreshTimer = view.setTimeout(refresh, FIND_REFRESH_MS);
    })
    : null;

  const open = () => {
    if (bar.hidden) {
      const active = doc.activeElement;
      returnFocus = active instanceof view.HTMLElement && active !== doc.body && !bar.contains(active)
        ? active
        : null;
      bar.hidden = false;
      observer?.observe(doc.body, OBSERVE);
      if (input.value.trim()) search();
      else render();
    }
    input.focus();
    input.select();
  };

  const shut = () => {
    if (bar.hidden) return;
    bar.hidden = true;
    observer?.disconnect();
    clearTimers();
    matches = [];
    capped = false;
    current = -1;
    unpaint();
    const back = returnFocus;
    returnFocus = null;
    if (back?.isConnected) back.focus({ preventScroll: true });
  };

  input.addEventListener('input', () => {
    if (typeTimer !== undefined) view.clearTimeout(typeTimer);
    typeTimer = view.setTimeout(search, FIND_TYPE_DEBOUNCE_MS);
  });
  input.addEventListener('keydown', (event) => {
    // Everything typed here stays here: no key in the box reaches the rest of the page.
    event.stopPropagation();
    if (event.isComposing) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      if (!settle()) move(event.shiftKey ? -1 : 1);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      shut();
    }
  });
  const step = (dir: 1 | -1) => () => {
    if (!settle()) move(dir);
    input.focus();
  };
  prev.addEventListener('click', step(-1));
  next.addEventListener('click', step(1));
  close.addEventListener('click', shut);

  const onKeyDown = (event: KeyboardEvent) => {
    // A trading hotkey the operator bound to Ctrl+F already handled it (window, capture).
    if (!isFindChord(event) || event.defaultPrevented) return;
    event.preventDefault();
    open();
  };
  doc.addEventListener('keydown', onKeyDown, true);

  const uninstall = () => {
    shut();
    doc.removeEventListener('keydown', onKeyDown, true);
    bar.remove();
    delete (doc as FindBarDocument).__novaFindBar;
  };
  (doc as FindBarDocument).__novaFindBar = uninstall;
  return uninstall;
}
