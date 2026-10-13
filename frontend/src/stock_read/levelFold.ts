/**
 * One label per price (operator report 2026-10-13, a 1-minute chart with fifteen names at its right edge: "there are
 * way too many lines here.. all the resistance level double bottom/tripple top.. top x5....."). Two tops 3c apart,
 * VWAP named twice, a round number 3c under the stop and the premarket high a cent under the entry each had a line and
 * a label of their own. Pure. What sits within `LEVEL_FOLD_PCT` of a stronger line folds into it -- its name joins
 * that line's label, its card that line's card -- in three places:
 * - the levels a pane picked, on one side of the price, are one band with one label (`levelPicks.ts`, `bands`);
 * - in the edge column, a level's or a trend line's name joins the nearest word over it in priority within reach: the
 *   plan's lines, VWAP, the high of day, a level (`foldColumn`). The EMAs, the LULD band and a flat top's word neither take
 *   nor give names, and the plan's lines never fold into each other;
 * - a lane's named line on the chart (the gap and go's premarket high) is the plan's word within reach (`foldSegments`).
 * A label that took others opens one card with each one's story (`foldedStory`).
 */
import { LEVEL_FOLD_PCT } from './constants';
import type { PriceLineSpec } from './chartShapes';
import type { ColumnItem } from './edgeColumn';
import type { ShapeStory } from './ShapeTip';
import type { Scene } from './sceneTypes';

const SEP = '|';
const FOLD = 'fold';

/** `b` within `pct` of `a`. */
export function near(a: number, b: number, pct = LEVEL_FOLD_PCT): boolean {
  return a > 0 && Math.abs(a - b) <= pct * a + 1e-9;
}

/** How far apart two words' lines are, a band's measured from its nearest edge; null past `pct` of the stronger one's
 * price. */
function reach(strong: ColumnItem, weak: ColumnItem, pct: number): number | null {
  const range = (it: ColumnItem) => it.span ?? { lo: it.price as number, hi: it.price as number };
  const a = range(strong);
  const b = range(weak);
  const gap = Math.max(0, b.lo - a.hi, a.lo - b.hi);
  return (strong.price as number) > 0 && gap <= pct * (strong.price as number) + 1e-9 ? gap : null;
}

/** The title and the parts a folded label's hover id names; null for any other id. */
export function foldParts(id: string): { title: string; ids: string[] } | null {
  if (!id.startsWith(`${FOLD}${SEP}`)) return null;
  const [, title, ...ids] = id.split(SEP);
  return { title, ids };
}

/** The hover id of a label that took others: its title and each part's own id (a fold's parts, flattened); null when
 * no part has a card. */
export function foldHoverId(title: string, ids: (string | null | undefined)[]): string | null {
  const parts = [...new Set(ids.flatMap(id => (id ? foldParts(id)?.ids ?? [id] : [])))];
  if (parts.length === 0) return null;
  return [FOLD, title.split(SEP).join('/'), ...parts].join(SEP);
}

/** A label with the names folded into it, each once and never one it already says. */
function withNames(text: string, names: string[]): string {
  const said = text.toLowerCase();
  const extra = [...new Set(names)].filter(n => n && !said.includes(n.toLowerCase()));
  return [text, ...extra].join(' · ');
}

/**
 * The column's words, each foldable one in view folded into the nearest word over it in priority whose line is within
 * reach (the stronger one where two are as near): gone from the column, its name after that word's, its card in that
 * word's card. A VWAP level folds into VWAP's tag, not into target 1 4c away. Weakest first, so a trend line that
 * folded into a level goes on with it. A tag for a price out of view stays a tag.
 */
export function foldColumn(items: ColumnItem[], height: number, pct = LEVEL_FOLD_PCT): ColumnItem[] {
  return foldColumnAt(items, height, pct).items;
}

/** `foldColumn`, saying which of `items` folded away (their indexes): a level that folded draws no line of its own,
 * the word it joined stands for it. */
export function foldColumnAt(items: ColumnItem[], height: number, pct = LEVEL_FOLD_PCT): { items: ColumnItem[];
  gone: Set<number> } {
  const inView = (it: ColumnItem) => it.price != null && it.y >= 0 && it.y <= height;
  const names: string[][] = items.map(() => []);
  const ids: (string | null)[][] = items.map(it => [it.hoverId]);
  const gone = new Set<number>();
  const order = items.map((_, i) => i).filter(i => items[i].foldName && inView(items[i]))
    .sort((a, b) => items[a].priority - items[b].priority);
  for (const i of order) {
    const it = items[i];
    let best = -1;
    let bestGap = Infinity;
    items.forEach((other, j) => {
      if (j === i || gone.has(j) || !other.absorbs || !inView(other) || other.priority <= it.priority) return;
      const gap = reach(other, it, pct);
      if (gap === null) return;
      if (gap < bestGap - 1e-9 || (Math.abs(gap - bestGap) <= 1e-9 && other.priority > items[best].priority)) {
        best = j;
        bestGap = gap;
      }
    });
    if (best < 0) continue;
    gone.add(i);
    names[best].push(it.foldName as string, ...names[i]);
    ids[best].push(...ids[i]);
  }
  const out = items.flatMap((it, i) => {
    if (gone.has(i)) return [];
    if (names[i].length === 0) return [it];
    return [{ ...it, text: withNames(it.text, names[i]), hoverId: foldHoverId(it.text, ids[i]) }];
  });
  return { items: out, gone };
}

/**
 * A lane's named line within reach of one of the plan's (the gap and go's premarket high a cent under its entry): its
 * name joins the plan's word -- the strategy box's, or the price line's title, which is the column's word -- and the
 * line and its label go. The plan's words that take names are the ones marked `absorbs`.
 */
export function foldSegments(scene: Scene, lines: PriceLineSpec[], pct = LEVEL_FOLD_PCT): { scene: Scene;
  lines: PriceLineSpec[] } {
  const words = [...(scene.words ?? [])];
  const outLines = [...lines];
  const segments = scene.segments.filter(s => {
    if (!s.name) return true;
    let best: { kind: 'word' | 'line'; i: number; d: number } | null = null;
    words.forEach((w, i) => {
      if (!w.absorbs || w.price === null || !near(w.price, s.price, pct)) return;
      const d = Math.abs(w.price - s.price);
      if (!best || d < best.d) best = { kind: 'word', i, d };
    });
    outLines.forEach((l, i) => {
      if (!l.title || !near(l.price, s.price, pct)) return;
      const d = Math.abs(l.price - s.price);
      if (!best || d < best.d) best = { kind: 'line', i, d };
    });
    const hit = best as { kind: 'word' | 'line'; i: number } | null;
    if (!hit) return true;
    if (hit.kind === 'word') words[hit.i] = { ...words[hit.i], text: withNames(words[hit.i].text, [s.name]) };
    else outLines[hit.i] = { ...outLines[hit.i], title: withNames(outLines[hit.i].title, [s.name]) };
    return false;
  });
  return { scene: { ...scene, segments, ...(scene.words ? { words } : {}) }, lines: outLines };
}

/**
 * The card of a label that took others: its title, then each part under its own title -- where it is and why it is
 * there -- and the parts' other sections once each ("What usually happens"), a repeated sentence once.
 */
export function foldedStory(id: string, one: (id: string) => ShapeStory | null): ShapeStory | null {
  const parts = foldParts(id);
  if (!parts) return null;
  const stories = parts.ids.map(one).filter((s): s is ShapeStory => s !== null);
  if (stories.length === 0) return null;
  const sections: { head: string; items: string[] }[] = [];
  const shared = new Map<string, string[]>();
  for (const s of stories) {
    const [first, ...rest] = s.sections ?? [];
    sections.push({ head: s.title, items: [...(s.subtitle ? [s.subtitle] : []), ...s.lines, ...(first?.items ?? [])] });
    for (const sec of rest) {
      const got = shared.get(sec.head) ?? [];
      for (const item of sec.items) if (!got.includes(item)) got.push(item);
      shared.set(sec.head, got);
    }
  }
  return {
    title: parts.title,
    color: stories[0].color,
    lines: [],
    sections: [...sections, ...[...shared].map(([head, items]) => ({ head, items }))],
  };
}
