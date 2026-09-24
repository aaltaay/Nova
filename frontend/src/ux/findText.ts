/**
 * Which text on the page matches a find (Ctrl+F, `ux/findBar.ts`), as DOM ranges.
 *
 * The page's text is read the way a person reads it: every text node under the
 * root in document order, joined inside one block (a cell, a row, a paragraph,
 * a button) and never across two -- so "3 of 12", which React writes as three
 * text nodes, is found, and the end of one cell never runs into the next. Case
 * is ignored, and a run of spaces in the query matches any spacing. Only what
 * is shown counts: text under a hidden element, in a tooltip, a script, a list
 * box or a text field is left out, and so is the find bar itself. Nothing here
 * reads layout except whether an element is shown.
 *
 * Owner: this module (pure over the DOM it is given; imports nothing, because
 * `main.tsx` installs the find bar before the app's constants may load).
 */

/** The find bar marks its own element with this; its text is never a match. */
export const FIND_BAR_ATTR = 'data-nova-find-bar';

/** Elements whose text is never page content a person reads. */
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SELECT', 'TEXTAREA', 'IFRAME', 'OBJECT']);
/** Elements that start a new run of text: a match never spans two of them. */
const BLOCK_TAGS = new Set([
  'ADDRESS', 'ARTICLE', 'ASIDE', 'BLOCKQUOTE', 'BODY', 'BUTTON', 'CAPTION', 'DD', 'DETAILS', 'DIALOG',
  'DIV', 'DL', 'DT', 'FIELDSET', 'FIGCAPTION', 'FIGURE', 'FOOTER', 'FORM', 'H1', 'H2', 'H3', 'H4', 'H5',
  'H6', 'HEADER', 'HR', 'LABEL', 'LEGEND', 'LI', 'MAIN', 'NAV', 'OL', 'P', 'PRE', 'SECTION', 'SUMMARY',
  'TABLE', 'TBODY', 'TD', 'TFOOT', 'TH', 'THEAD', 'TR', 'UL',
]);
/** Between two blocks in the joined text: never whitespace, so no query spans the two. */
const BLOCK_BREAK = '\u0000';
const SHOW_ELEMENT_AND_TEXT = 0x1 | 0x4;
const FILTER_ACCEPT = 1;
const FILTER_REJECT = 2;
const FILTER_SKIP = 3;
const TEXT_NODE = 3;

export interface FindMatch {
  range: Range;
  /** Where the match starts: the bar keeps the current match by it when the page changes. */
  node: Text;
  offset: number;
}

export interface FindResult {
  matches: FindMatch[];
  /** More were shown than the limit: the count reads "N+". */
  capped: boolean;
}

interface Piece {
  node: Text;
  /** Where the node's text starts in the joined text. */
  start: number;
}

/** The query as a pattern -- case ignored, a run of spaces matching any spacing; null when empty. */
export function findPattern(query: string): RegExp | null {
  const words = query.trim().split(/\s+/u).filter(Boolean);
  if (words.length === 0) return null;
  const escaped = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&'));
  return new RegExp(escaped.join('\\s+'), 'giu');
}

function isBlock(el: Element): boolean {
  // An SVG <text> is its own label (a chart axis), never joined to the next one.
  return BLOCK_TAGS.has(el.tagName) || el.localName === 'text';
}

function blockOf(el: Element, root: Element, cache: Map<Element, Element>): Element {
  const hit = cache.get(el);
  if (hit) return hit;
  let cur: Element | null = el;
  while (cur && cur !== root && !isBlock(cur)) cur = cur.parentElement;
  const block = cur ?? root;
  cache.set(el, block);
  return block;
}

function skipped(el: Element): boolean {
  return SKIP_TAGS.has(el.tagName) || el.hasAttribute(FIND_BAR_ATTR) || el.getAttribute('role') === 'tooltip';
}

/** Every readable text node under `root` joined into one string, with where each node starts. */
function readText(root: Element): { text: string; pieces: Piece[] } {
  const walker = root.ownerDocument.createTreeWalker(root, SHOW_ELEMENT_AND_TEXT, {
    acceptNode(node: Node): number {
      if (node.nodeType === TEXT_NODE) return FILTER_ACCEPT;
      return skipped(node as Element) ? FILTER_REJECT : FILTER_SKIP;
    },
  });
  const parts: string[] = [];
  const pieces: Piece[] = [];
  const blocks = new Map<Element, Element>();
  let length = 0;
  let lastBlock: Element | null = null;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node as Text;
    const parent = text.parentElement;
    if (!text.data || !parent) continue;
    const block = blockOf(parent, root, blocks);
    if (lastBlock && block !== lastBlock) {
      parts.push(BLOCK_BREAK);
      length += BLOCK_BREAK.length;
    }
    lastBlock = block;
    pieces.push({ node: text, start: length });
    parts.push(text.data);
    length += text.data.length;
  }
  return { text: parts.join(''), pieces };
}

/** The piece that holds position `pos` of the joined text (the last one starting at or before it). */
function pieceAt(pieces: Piece[], pos: number): Piece {
  let lo = 0;
  let hi = pieces.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (pieces[mid].start <= pos) lo = mid;
    else hi = mid - 1;
  }
  return pieces[lo];
}

/** Shown on the page: not under `display: none`, `visibility: hidden` or a `hidden` element. */
function isShown(el: Element, cache: Map<Element, boolean>): boolean {
  let shown = cache.get(el);
  if (shown === undefined) {
    shown = typeof el.checkVisibility === 'function'
      ? el.checkVisibility({ checkVisibilityCSS: true, visibilityProperty: true })
      : !el.closest('[hidden]');
    cache.set(el, shown);
  }
  return shown;
}

/** Every shown match of `query` under `root`, in page order, at most `limit`. */
export function findMatches(root: Element, query: string, limit: number): FindResult {
  const pattern = findPattern(query);
  if (!pattern) return { matches: [], capped: false };
  const { text, pieces } = readText(root);
  if (pieces.length === 0) return { matches: [], capped: false };
  const doc = root.ownerDocument;
  const shown = new Map<Element, boolean>();
  const matches: FindMatch[] = [];
  for (const hit of text.matchAll(pattern)) {
    if (!hit[0]) continue;
    const start = hit.index ?? 0;
    const end = start + hit[0].length;
    const first = pieceAt(pieces, start);
    const last = pieceAt(pieces, end - 1);
    const parent = first.node.parentElement;
    if (!parent || !isShown(parent, shown)) continue;
    if (matches.length >= limit) return { matches, capped: true };
    const range = doc.createRange();
    range.setStart(first.node, start - first.start);
    range.setEnd(last.node, end - last.start);
    matches.push({ range, node: first.node, offset: start - first.start });
  }
  return { matches, capped: false };
}
