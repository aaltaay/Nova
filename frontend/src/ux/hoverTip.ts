/**
 * What a chip or a number means -- one tip for the whole desk (operator ask
 * 2026-09-24: "we are going to need lots of hovers, explaining in detail what
 * each means", ADR 031).
 *
 * The convention: an element that explains itself carries its explanation in
 * `data-tip` (plain text; line breaks kept) and, optionally, a short heading in
 * `data-tip-title`. This module owns the one tip that shows them:
 *
 * - hovering such an element shows the tip after `HOVER_TIP_DELAY_MS`, and
 *   moving on to another one answers at once;
 * - keyboard focus shows it too, so a tabbed-to chip explains itself;
 * - the text is re-read while the tip is up, so a live number ("4c under the
 *   trigger") stays current under the pointer;
 * - Escape, a scroll or a resize hides it.
 *
 * A locked control keeps `data-why` (`ux/whyTip.ts`): when an element carries
 * both and is locked, this tip stays out of the way, so the two never stack.
 * The text goes in with `textContent`, never as HTML. Use `title` for a short
 * label the browser may show late; use `data-tip` for anything that explains.
 *
 * Owner: this module. `installHoverTip` runs once per window from `main.tsx`.
 */
import './hoverTip.css';

/** The attributes an element explains itself with. */
export const TIP_ATTR = 'data-tip';
export const TIP_TITLE_ATTR = 'data-tip-title';
/** Long enough not to flicker across a table; short enough to feel like an answer. */
export const HOVER_TIP_DELAY_MS = 250;
/** While the tip is up its text is re-read this often (live numbers move). */
export const HOVER_TIP_REFRESH_MS = 500;
const GAP_PX = 8;
const EDGE_PX = 8;
const TIP_ID = 'nova-hover-tip';
const LOCKED_WITH_WHY = '[data-why]:disabled, [data-why][aria-disabled="true"]';

/** `data-tip` / `data-tip-title` for an element, `{...tipProps(text, title)}`; nothing for an empty text. */
export function tipProps(text: string | null | undefined, title?: string | null): Record<string, string> {
  const body = text?.trim();
  if (!body) return {};
  const head = title?.trim();
  return head ? { [TIP_ATTR]: body, [TIP_TITLE_ATTR]: head } : { [TIP_ATTR]: body };
}

/** The element a pointer / focus event landed on that explains itself, if any. */
export function tipTarget(node: EventTarget | null): HTMLElement | null {
  if (!node || typeof (node as Element).closest !== 'function') return null;
  const el = (node as Element).closest<HTMLElement>(`[${TIP_ATTR}]`);
  if (!el || !el.getAttribute(TIP_ATTR)?.trim()) return null;
  if (el.matches(LOCKED_WITH_WHY)) return null;     // the why-tip answers for a locked control
  return el;
}

function isInside(root: Element, node: EventTarget | null): boolean {
  return Boolean(node) && node instanceof Node && root.contains(node);
}

/** Install the tip on `doc` (idempotent per document). Returns the uninstall (tests). */
export function installHoverTip(doc: Document = document): () => void {
  const view = doc.defaultView;
  if (!view || !doc.body) return () => undefined;
  const existing = (doc as Document & { __novaHoverTip?: () => void }).__novaHoverTip;
  if (existing) return existing;

  const tip = doc.createElement('div');
  tip.id = TIP_ID;
  tip.className = 'hover-tip';
  tip.setAttribute('role', 'tooltip');
  tip.hidden = true;
  const head = doc.createElement('div');
  head.className = 'hover-tip__title';
  const body = doc.createElement('div');
  body.className = 'hover-tip__body';
  tip.append(head, body);
  doc.body.appendChild(tip);

  let current: HTMLElement | null = null;
  let pending: HTMLElement | null = null;
  let showTimer: number | undefined;
  let refreshTimer: number | undefined;
  let shownText = '';

  const clearShow = () => {
    if (showTimer !== undefined) view.clearTimeout(showTimer);
    showTimer = undefined;
    pending = null;
  };

  const place = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const vw = doc.documentElement.clientWidth || view.innerWidth;
    const vh = doc.documentElement.clientHeight || view.innerHeight;
    let top = r.bottom + GAP_PX;
    if (top + t.height > vh - EDGE_PX && r.top - GAP_PX - t.height >= EDGE_PX) {
      top = r.top - GAP_PX - t.height;
    }
    const maxLeft = Math.max(EDGE_PX, vw - EDGE_PX - t.width);
    const left = Math.min(Math.max(r.left + r.width / 2 - t.width / 2, EDGE_PX), maxLeft);
    tip.style.top = `${Math.round(top)}px`;
    tip.style.left = `${Math.round(left)}px`;
  };

  const fill = (el: HTMLElement): boolean => {
    const text = el.getAttribute(TIP_ATTR)?.trim() ?? '';
    const title = el.getAttribute(TIP_TITLE_ATTR)?.trim() ?? '';
    if (!text) return false;
    const key = `${title}\u0000${text}`;
    if (key === shownText) return true;
    shownText = key;
    head.textContent = title;
    head.hidden = !title;
    body.textContent = text;
    return true;
  };

  const stopRefresh = () => {
    if (refreshTimer !== undefined) view.clearInterval(refreshTimer);
    refreshTimer = undefined;
  };

  const hide = () => {
    clearShow();
    stopRefresh();
    current = null;
    shownText = '';
    tip.hidden = true;
  };

  const show = (el: HTMLElement) => {
    clearShow();
    if (!fill(el)) return;
    current = el;
    tip.hidden = false;
    place(el);
    stopRefresh();
    refreshTimer = view.setInterval(() => {
      // Gone, or locked since (the why-tip answers for it now): never two tips at once.
      if (!current || !current.isConnected || current.matches(LOCKED_WITH_WHY)) {
        hide();
        return;
      }
      if (!fill(current)) {
        hide();
        return;
      }
      place(current);
    }, HOVER_TIP_REFRESH_MS);
  };

  const onOver = (e: Event) => {
    const el = tipTarget(e.target);
    if (!el || el === current || el === pending) return;
    if (current) {
      show(el);                    // moving between explained chips: answer at once
      return;
    }
    clearShow();
    pending = el;
    showTimer = view.setTimeout(() => {
      showTimer = undefined;
      pending = null;
      show(el);
    }, HOVER_TIP_DELAY_MS);
  };

  const onOut = (e: Event) => {
    const related = (e as MouseEvent).relatedTarget ?? null;
    if (pending && !isInside(pending, related)) clearShow();
    if (current && !isInside(current, related)) {
      const next = tipTarget(related);
      if (next) show(next);
      else hide();
    }
  };

  const onFocusIn = (e: Event) => {
    const el = tipTarget(e.target);
    if (el && el !== current) show(el);
  };

  const onFocusOut = (e: Event) => {
    if (current && isInside(current, e.target)) hide();
  };

  const onKey = (e: Event) => {
    if ((e as KeyboardEvent).key === 'Escape' && current) hide();
  };

  const onMove = () => {
    if (current) hide();
  };

  const opts = { capture: true };
  const passive = { capture: true, passive: true };
  doc.addEventListener('pointerover', onOver, opts);
  doc.addEventListener('pointerout', onOut, opts);
  doc.addEventListener('pointerdown', onMove, opts);
  doc.addEventListener('focusin', onFocusIn, opts);
  doc.addEventListener('focusout', onFocusOut, opts);
  doc.addEventListener('keydown', onKey, opts);
  doc.addEventListener('scroll', onMove, passive);
  view.addEventListener('resize', onMove);

  const uninstall = () => {
    hide();
    doc.removeEventListener('pointerover', onOver, opts);
    doc.removeEventListener('pointerout', onOut, opts);
    doc.removeEventListener('pointerdown', onMove, opts);
    doc.removeEventListener('focusin', onFocusIn, opts);
    doc.removeEventListener('focusout', onFocusOut, opts);
    doc.removeEventListener('keydown', onKey, opts);
    doc.removeEventListener('scroll', onMove, passive);
    view.removeEventListener('resize', onMove);
    tip.remove();
    delete (doc as Document & { __novaHoverTip?: () => void }).__novaHoverTip;
  };
  (doc as Document & { __novaHoverTip?: () => void }).__novaHoverTip = uninstall;
  return uninstall;
}
