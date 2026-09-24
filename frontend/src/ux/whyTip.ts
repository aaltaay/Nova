/**
 * Why a control is locked -- one tip for the whole desk (operator report
 * 2026-09-23: "these are always unclickable, at least it should explain why").
 *
 * The convention: a control that cannot act right now carries its reason in
 * `data-why`, beside `disabled` (or `aria-disabled="true"` on anything that is
 * not a form control, such as a label or a menu row). This module owns the one
 * tip that shows that reason:
 *
 * - hovering a locked control shows it after `WHY_TIP_HOVER_MS`;
 * - pressing one shows it at once and holds it for `WHY_TIP_PRESS_HOLD_MS`, so a
 *   refused press never does nothing;
 * - a click on an `aria-disabled` control that carries a reason is swallowed
 *   here, so "locked" means locked for mouse and keyboard alike.
 *
 * A disabled form control never receives `click`, but Chromium delivers
 * `pointerover` / `pointerdown` to it (checked on Chromium 149), so one
 * listener on the document serves every control in every window -- the main
 * desk, the pop-out Trader windows and the sample desk. A `data-why` left on a
 * control that is enabled again shows nothing: only a locked control explains
 * itself. The reason goes in `data-why`, not `title`: the native tooltip comes
 * late, cannot be styled, and would stack on this one.
 *
 * Owner: this module. `installWhyTip` runs once per window from `main.tsx`;
 * `whyCoverage.test.ts` keeps every disabled control in `src/` carrying a reason.
 */
import './whyTip.css';

/** The attribute a locked control carries its reason in. */
export const WHY_ATTR = 'data-why';
/** Hover delay before the tip shows -- long enough not to flicker across a toolbar. */
export const WHY_TIP_HOVER_MS = 120;
/** A refused press keeps its reason up this long, even when the pointer moves on. */
export const WHY_TIP_PRESS_HOLD_MS = 3500;
const WHY_TIP_GAP_PX = 6;
const WHY_TIP_EDGE_PX = 8;
const WHY_TIP_ID = 'nova-why-tip';
const LOCKED_SELECTOR = ':disabled, [aria-disabled="true"]';

/** `data-why` only while `locked`: spread onto a control, `{...whyProps(locked, reason)}`. */
export function whyProps(locked: boolean, reason: string | null | undefined): { 'data-why'?: string } {
  const text = reason?.trim();
  return locked && text ? { 'data-why': text } : {};
}

/**
 * The locked control a pointer / focus event landed on, when it carries a
 * reason -- or the locked control a hovered `<label>` names, so the words
 * beside a locked checkbox explain it too.
 */
export function lockedTarget(node: EventTarget | null): HTMLElement | null {
  if (!node || typeof (node as Element).closest !== 'function') return null;
  const el = (node as Element).closest<HTMLElement>(`[${WHY_ATTR}]`);
  if (el && el.getAttribute(WHY_ATTR)?.trim() && el.matches(LOCKED_SELECTOR)) return el;
  const control = (node as Element).closest('label')?.control as HTMLElement | null | undefined;
  if (control && control.getAttribute(WHY_ATTR)?.trim() && control.matches(LOCKED_SELECTOR)) return control;
  return null;
}

function isInside(root: Element, node: EventTarget | null): boolean {
  return Boolean(node) && node instanceof Node && root.contains(node);
}

/**
 * Install the tip on `doc` (idempotent per document). Returns the uninstall,
 * which removes the listeners and the tip element (tests).
 */
export function installWhyTip(doc: Document = document): () => void {
  const view = doc.defaultView;
  if (!view || !doc.body) return () => undefined;
  const existing = (doc as Document & { __novaWhyTip?: () => void }).__novaWhyTip;
  if (existing) return existing;

  const tip = doc.createElement('div');
  tip.id = WHY_TIP_ID;
  tip.className = 'why-tip';
  tip.setAttribute('role', 'tooltip');
  tip.hidden = true;
  doc.body.appendChild(tip);

  let current: HTMLElement | null = null;
  let pending: HTMLElement | null = null;
  let showTimer: number | undefined;
  let holdTimer: number | undefined;
  let held = false;
  let hovered: HTMLElement | null = null;

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
    let top = r.bottom + WHY_TIP_GAP_PX;
    if (top + t.height > vh - WHY_TIP_EDGE_PX && r.top - WHY_TIP_GAP_PX - t.height >= WHY_TIP_EDGE_PX) {
      top = r.top - WHY_TIP_GAP_PX - t.height;
    }
    const maxLeft = Math.max(WHY_TIP_EDGE_PX, vw - WHY_TIP_EDGE_PX - t.width);
    const left = Math.min(Math.max(r.left + r.width / 2 - t.width / 2, WHY_TIP_EDGE_PX), maxLeft);
    tip.style.top = `${Math.round(top)}px`;
    tip.style.left = `${Math.round(left)}px`;
  };

  const show = (el: HTMLElement, pressed: boolean) => {
    clearShow();
    const text = el.getAttribute(WHY_ATTR)?.trim();
    if (!text) return;
    current = el;
    tip.textContent = text;
    tip.hidden = false;
    tip.classList.remove('why-tip--pressed');
    if (pressed) {
      // Restart the pulse: a second refused press should read as a second answer.
      void tip.offsetWidth;
      tip.classList.add('why-tip--pressed');
    }
    place(el);
  };

  const hide = () => {
    clearShow();
    current = null;
    tip.hidden = true;
    tip.classList.remove('why-tip--pressed');
  };

  const release = () => {
    if (holdTimer !== undefined) view.clearTimeout(holdTimer);
    holdTimer = undefined;
    held = false;
  };

  const onOver = (e: Event) => {
    const el = lockedTarget(e.target);
    hovered = el;
    if (!el) return;
    if (el === current || el === pending) return;
    if (current && !held) {
      show(el, false); // moving between locked controls: answer at once
      return;
    }
    clearShow();
    pending = el;
    showTimer = view.setTimeout(() => {
      showTimer = undefined;
      pending = null;
      if (!held) show(el, false);
    }, WHY_TIP_HOVER_MS);
  };

  const onOut = (e: Event) => {
    const related = (e as MouseEvent).relatedTarget ?? null;
    if (pending && !isInside(pending, related)) clearShow();
    if (hovered && !isInside(hovered, related)) hovered = null;
    if (current && !held && !isInside(current, related)) hide();
  };

  const onDown = (e: Event) => {
    const el = lockedTarget(e.target);
    if (!el) {
      if (current && !isInside(current, e.target)) {
        release();
        hide();
      }
      return;
    }
    release();
    show(el, true);
    held = true;
    holdTimer = view.setTimeout(() => {
      holdTimer = undefined;
      held = false;
      if (hovered !== current) hide();
    }, WHY_TIP_PRESS_HOLD_MS);
  };

  // A locked aria-disabled control stays locked: its click (mouse or Enter / Space)
  // never reaches its handler. Native :disabled controls never get the click anyway.
  const onClick = (e: Event) => {
    const el = lockedTarget(e.target);
    if (!el || !el.matches('[aria-disabled="true"]')) return;
    e.preventDefault();
    e.stopPropagation();
    if (current !== el) show(el, true);
  };

  const onFocusIn = (e: Event) => {
    const el = lockedTarget(e.target);
    if (el && el !== current) show(el, false);
  };

  const onFocusOut = (e: Event) => {
    if (current && !held && isInside(current, e.target) && hovered !== current) hide();
  };

  const onKey = (e: Event) => {
    if ((e as KeyboardEvent).key === 'Escape' && current) {
      release();
      hide();
    }
  };

  const onMove = () => {
    if (!current) return;
    release();
    hide();
  };

  const opts = { capture: true };
  const passive = { capture: true, passive: true };
  doc.addEventListener('pointerover', onOver, opts);
  doc.addEventListener('pointerout', onOut, opts);
  doc.addEventListener('pointerdown', onDown, opts);
  doc.addEventListener('click', onClick, opts);
  doc.addEventListener('focusin', onFocusIn, opts);
  doc.addEventListener('focusout', onFocusOut, opts);
  doc.addEventListener('keydown', onKey, opts);
  doc.addEventListener('scroll', onMove, passive);
  view.addEventListener('resize', onMove);

  const uninstall = () => {
    release();
    hide();
    doc.removeEventListener('pointerover', onOver, opts);
    doc.removeEventListener('pointerout', onOut, opts);
    doc.removeEventListener('pointerdown', onDown, opts);
    doc.removeEventListener('click', onClick, opts);
    doc.removeEventListener('focusin', onFocusIn, opts);
    doc.removeEventListener('focusout', onFocusOut, opts);
    doc.removeEventListener('keydown', onKey, opts);
    doc.removeEventListener('scroll', onMove, passive);
    view.removeEventListener('resize', onMove);
    tip.remove();
    delete (doc as Document & { __novaWhyTip?: () => void }).__novaWhyTip;
  };
  (doc as Document & { __novaWhyTip?: () => void }).__novaWhyTip = uninstall;
  return uninstall;
}
