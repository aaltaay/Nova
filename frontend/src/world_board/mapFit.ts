/**
 * Where a world board's map sits in its box (the Global and Forex pages, ADR 060, 061): the view fitted whole and
 * centred, labels that stay 11-13 px on screen whatever the map's scale, and a hover card beside its bubble on the
 * side with room.
 */
import type { CSSProperties } from 'react';
import type { Box } from './useBox';
import { WORLD_VIEW } from './worldLand';

const TIP_WIDTH = 290;               // the Global page's .gb-tip outer width (border-box)
const TIP_GAP = 16;

/** Where the drawn map sits in its box: the view fitted whole and centred. */
export function fit(box: Box): { k: number; ox: number; oy: number } {
  const k = Math.min(box.width / WORLD_VIEW.width, box.height / WORLD_VIEW.height);
  return { k, ox: (box.width - WORLD_VIEW.width * k) / 2, oy: (box.height - WORLD_VIEW.height * k) / 2 };
}

/** The label size in view units that shows as 11-13 px on screen (12 when the map is drawn about life size). */
export function labelSize(k: number): number {
  return Math.min(Math.max(12, 11 / k), 13 / k);
}

/** The card's place in the box: right of the bubble unless that runs out of room, below its top half, above its lower. */
export function tipPlace(x: number, y: number, box: Box, width = TIP_WIDTH): CSSProperties {
  const left = x + TIP_GAP + width <= box.width ? x + TIP_GAP : Math.max(0, x - TIP_GAP - width);
  return y <= box.height / 2
    ? { left, top: Math.max(0, y - 30) }
    : { left, bottom: Math.max(0, box.height - y - 30) };
}
