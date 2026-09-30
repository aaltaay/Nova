/**
 * The export page's drawing, pure math plus one canvas routine: a crop fitted
 * into the output without stretching (black bars when a later geometry has
 * another shape), blur boxes carried through the same fit, and the frame times
 * of a piece at the output's constant frame rate.
 */
export type Box = { x: number; y: number; w: number; h: number };
export type Fit = Box & { scale: number };

/** `crop` scaled to fit `outW` x `outH`, centred. */
export function fitRect(crop: Box, outW: number, outH: number): Fit {
  const scale = Math.min(outW / crop.w, outH / crop.h);
  const w = crop.w * scale;
  const h = crop.h * scale;
  return { x: (outW - w) / 2, y: (outH - h) / 2, w, h, scale };
}

/** A box in the crop's source pixels, in output pixels. */
export function mapBox(box: Box, fit: Fit): Box {
  return { x: fit.x + box.x * fit.scale, y: fit.y + box.y * fit.scale, w: box.w * fit.scale, h: box.h * fit.scale };
}

/** A picture in DIP inside the window's page, with the page's size: a high-quality piece's (clipExportPlan.mjs). */
export type WindowSpec = { dip: Box | null; content: { width: number; height: number }; blur: Box[] };

/**
 * A window capture's crop and blur boxes for one decoded frame of `fw` x `fh`.
 * Measured on the desk's three monitors (2026-09-29, 100% and 150%): the frame
 * is the window's visible rectangle, the page sits at its bottom-left at the
 * capture's scale under the title bar, and its last DIP row is not in the
 * frame. `dip: null` is the whole frame (title bar and all).
 */
export function windowCrop(spec: WindowSpec, fw: number, fh: number): { crop: Box; blur: Box[] } | null {
  const s = fw / Math.max(1, spec.content.width);
  const offY = Math.max(0, fh - (spec.content.height - 1) * s);
  const toFrame = (d: Box): Box => ({ x: d.x * s, y: offY + d.y * s, w: d.w * s, h: d.h * s });
  const crop = spec.dip ? clamp(toFrame(spec.dip), fw, fh) : { x: 0, y: 0, w: fw, h: fh };
  if (!crop) return null;
  const blur: Box[] = [];
  for (const d of spec.blur) {
    const px = toFrame(d);
    const x0 = Math.max(0, px.x - crop.x);
    const y0 = Math.max(0, px.y - crop.y);
    const x1 = Math.min(crop.w, px.x + px.w - crop.x);
    const y1 = Math.min(crop.h, px.y + px.h - crop.y);
    if (x1 - x0 >= 2 && y1 - y0 >= 2) blur.push({ x: x0, y: y0, w: x1 - x0, h: y1 - y0 });
  }
  return { crop, blur };
}

function clamp(r: Box, fw: number, fh: number): Box | null {
  const x0 = Math.max(0, Math.floor(r.x));
  const y0 = Math.max(0, Math.floor(r.y));
  const x1 = Math.min(fw, Math.ceil(r.x + r.w));
  const y1 = Math.min(fh, Math.ceil(r.y + r.h));
  return x1 - x0 >= 2 && y1 - y0 >= 2 ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null;
}

/** Source times `t0, t0 + 1/fps, ...` before `t1` (at least one). */
export function frameTimes(t0: number, t1: number, fps: number): number[] {
  const n = Math.max(1, Math.round((t1 - t0) * fps));
  const step = 1 / fps;
  return Array.from({ length: n }, (_, i) => t0 + i * step);
}

type Ctx = OffscreenCanvasRenderingContext2D;
type Drawable = { draw: (ctx: Ctx, sx: number, sy: number, sw: number, sh: number, dx: number, dy: number, dw: number, dh: number) => void };

let scratch: OffscreenCanvas | null = null;

/**
 * Blur a box of the canvas in place: shrink it to a sixteenth and back up
 * twice, which reads as a blur and costs two small draws. Text inside it is
 * never legible afterwards.
 */
export function blurBox(ctx: Ctx, box: Box): void {
  const w = Math.max(1, Math.round(box.w));
  const h = Math.max(1, Math.round(box.h));
  const sw = Math.max(1, Math.round(w / 16));
  const sh = Math.max(1, Math.round(h / 16));
  if (!scratch) scratch = new OffscreenCanvas(sw, sh);
  if (scratch.width < sw || scratch.height < sh) {
    scratch.width = Math.max(scratch.width, sw);
    scratch.height = Math.max(scratch.height, sh);
  }
  const s = scratch.getContext('2d');
  if (!s) return;
  for (let pass = 0; pass < 2; pass += 1) {
    s.imageSmoothingEnabled = true;
    s.clearRect(0, 0, sw, sh);
    s.drawImage(ctx.canvas, box.x, box.y, w, h, 0, 0, sw, sh);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(scratch, 0, 0, sw, sh, box.x, box.y, w, h);
  }
}

/** One output frame: black, the crop fitted in, then the blur boxes. A null sample keeps the last frame. */
export function drawFrame(ctx: Ctx, sample: Drawable | null, crop: Box, outW: number, outH: number, blur: Box[]): void {
  if (!sample) return;
  const fit = fitRect(crop, outW, outH);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, outW, outH);
  sample.draw(ctx, crop.x, crop.y, crop.w, crop.h, fit.x, fit.y, fit.w, fit.h);
  for (const b of blur) blurBox(ctx, mapBox(b, fit));
}
