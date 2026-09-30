/**
 * The words on the 1-minute pane's drawings (ADR 036; operator report 2026-09-30: "i do really like
 * seeing the details, but perhaps it is extremely too crowded"): where each label goes and how it is
 * drawn. The live lanes' labels, the levels' words and the moment's pin stay where they are. A past
 * setup's label makes room: it comes whole, short and as icons (`pastSetups.ts` has the words), and the
 * past labels take what room is left -- a trigger's result first, then the newest -- each the longest
 * form the operator's setting allows that runs into nothing already placed, and none when even its
 * icons would. Its box and its hover stay either way. `placeLabels` takes the text measure as an
 * argument, so it runs without a canvas.
 */

/** How much a past setup's label says: `compact` a few words, `full` the whole label where it fits. */
export type LabelDetail = 'compact' | 'full';

export const LABEL_FONT = '600 10px ui-sans-serif, system-ui, sans-serif';
const PIN_FONT = '700 9px ui-sans-serif, system-ui, sans-serif';
export const LABEL_H = 14;
const PIN_H = 14;
/** Padding either side of a label's text. */
const LABEL_PAD_PX = 4;
/** Room kept clear between two labels, and from the pane's edges. */
const LABEL_GAP_PX = 1;
const EDGE_PX = 2;

export interface LabelRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** A past setup's shorter forms and its claim to the room (higher first: the newest setups). */
export interface LabelShrink {
  short: string | null;
  icon: string | null;
  rank: number;
}

/** One label to place: where its box puts it, and the forms it may take, longest first. */
export interface LabelAsk {
  forms: string[];
  /** The left edge it starts from (its box's), and its middle. */
  x: number;
  y: number;
  /** Placed whole where it is, whatever it runs into (a live lane's). */
  fixed: boolean;
  rank: number;
}

export interface PlacedLabel {
  /** The ask's index. */
  ask: number;
  text: string;
  left: number;
  width: number;
  y: number;
}

/** The forms a box's label may take under the operator's setting, longest first. */
export function labelForms(label: string | null, shrink: LabelShrink | undefined, detail: LabelDetail): string[] {
  if (!shrink) return label ? [label] : [];
  const forms = detail === 'full' ? [label, shrink.short, shrink.icon] : [shrink.short, shrink.icon];
  const out: string[] = [];
  for (const f of forms) if (f && !out.includes(f)) out.push(f);
  return out;
}

/** A label's rectangle: `align` left starts it at `x`, right ends it there; kept inside the pane. */
export function labelRect(x: number, y: number, width: number, align: 'left' | 'right', paneWidth: number): LabelRect {
  let left = align === 'left' ? x : x - width;
  if (paneWidth > 0) left = Math.max(EDGE_PX, Math.min(left, paneWidth - width - EDGE_PX));
  return { left, top: y - LABEL_H / 2, right: left + width, bottom: y + LABEL_H / 2 };
}

function touches(a: LabelRect, b: LabelRect): boolean {
  return a.left < b.right + LABEL_GAP_PX && a.right + LABEL_GAP_PX > b.left
    && a.top < b.bottom + LABEL_GAP_PX && a.bottom + LABEL_GAP_PX > b.top;
}

/**
 * Where each label goes, and what it says: fixed labels first, where they are; then the rest by rank,
 * each the first of its forms that touches nothing placed (`obstacles` included), or nothing.
 * `measure` is a label's whole width (text and padding). Returned in the asks' order, the order drawn.
 */
export function placeLabels(
  asks: LabelAsk[],
  measure: (text: string) => number,
  paneWidth: number,
  obstacles: LabelRect[] = [],
): PlacedLabel[] {
  const order = asks.map((_, i) => i).sort((a, b) => {
    const fa = asks[a].fixed ? 1 : 0;
    const fb = asks[b].fixed ? 1 : 0;
    return fb - fa || asks[b].rank - asks[a].rank || a - b;
  });
  const taken = [...obstacles];
  const out: PlacedLabel[] = [];
  for (const i of order) {
    const ask = asks[i];
    for (const text of ask.forms) {
      const width = measure(text);
      const r = labelRect(ask.x, ask.y, width, 'left', paneWidth);
      if (!ask.fixed && taken.some(t => touches(r, t))) continue;
      taken.push(r);
      out.push({ ask: i, text, left: r.left, width, y: ask.y });
      break;
    }
  }
  return out.sort((a, b) => a.ask - b.ask);
}

/** A label's whole width on `ctx`. */
export function labelMeasure(ctx: CanvasRenderingContext2D): (text: string) => number {
  return (text: string) => {
    ctx.font = LABEL_FONT;
    return ctx.measureText(text).width + 2 * LABEL_PAD_PX;
  };
}

export function drawLabel(ctx: CanvasRenderingContext2D, text: string, left: number, y: number, width: number,
  color: string): void {
  ctx.font = LABEL_FONT;
  ctx.fillStyle = 'rgba(12, 12, 14, 0.78)';
  ctx.fillRect(left, y - LABEL_H / 2, width, LABEL_H);
  ctx.fillStyle = color;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillText(text, left + LABEL_PAD_PX, y + 0.5);
}

/** A filled tag over a price on one candle, on a stem down to the price. */
export interface PinSpec {
  label: string;
  color: string;
}

/** Where a pin's tag sits over (`x`, `y`). */
export function pinRect(ctx: CanvasRenderingContext2D, x: number, y: number, label: string, paneWidth: number): LabelRect {
  ctx.font = PIN_FONT;
  const w = ctx.measureText(label).width + 10;
  const left = Math.min(Math.max(EDGE_PX, x - w / 2), paneWidth - w - EDGE_PX);
  const top = Math.max(EDGE_PX, y - PIN_H - 7);
  return { left, top, right: left + w, bottom: top + PIN_H };
}

/** Dark ink on a light fill, white on a dark one. */
function inkFor(color: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(color);
  if (!m) return '#ffffff';
  const n = parseInt(m[1], 16);
  const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return lum > 0.55 ? '#0b0d12' : '#ffffff';
}

export function drawPin(ctx: CanvasRenderingContext2D, x: number, y: number, p: PinSpec, r: LabelRect): void {
  ctx.strokeStyle = p.color;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(Math.round(x) + 0.5, r.bottom);
  ctx.lineTo(Math.round(x) + 0.5, y);
  ctx.stroke();
  ctx.fillStyle = p.color;
  ctx.beginPath();
  const w = r.right - r.left;
  if (typeof ctx.roundRect === 'function') ctx.roundRect(r.left, r.top, w, PIN_H, 3);
  else ctx.rect(r.left, r.top, w, PIN_H);
  ctx.fill();
  ctx.font = PIN_FONT;
  ctx.fillStyle = inkFor(p.color);
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'center';
  ctx.fillText(p.label, r.left + w / 2, r.top + PIN_H / 2 + 0.5);
}
