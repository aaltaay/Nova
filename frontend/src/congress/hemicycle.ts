/**
 * A chamber's seat map (ADR 066): every seat on concentric arcs, Democrats from the left, then independents, then
 * Republicans -- seated by party only (the House has no assigned seats; this is not the floor chart). Pure.
 */
import type { Member } from './types';

export interface Spot {
  x: number;
  y: number;
}

/** `n` seat centres on `rows` arcs from radius `r0` to `r1` around (cx, cy), ordered left to right across the arc. */
export function hemicycle(n: number, rows: number, r0: number, r1: number, cx: number, cy: number): Spot[] {
  if (n <= 0) return [];
  const radii = Array.from({ length: rows }, (_, i) => (rows === 1 ? r1 : r0 + ((r1 - r0) * i) / (rows - 1)));
  const total = radii.reduce((a, b) => a + b, 0);
  const counts = radii.map((r) => Math.round((n * r) / total));
  counts[counts.length - 1] += n - counts.reduce((a, b) => a + b, 0);
  const spots: { angle: number; r: number }[] = [];
  radii.forEach((r, i) => {
    const k = counts[i];
    for (let j = 0; j < k; j += 1) spots.push({ angle: k > 1 ? Math.PI * (1 - j / (k - 1)) : Math.PI / 2, r });
  });
  spots.sort((a, b) => b.angle - a.angle || a.r - b.r);
  return spots.map(({ angle, r }) => ({ x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle) }));
}

const PARTY_ORDER: Record<string, number> = { D: 0, I: 1, R: 2 };

/** Members in seat order: by party (D, I, R; anyone else after), then state, then name. */
export function seatOrder(members: readonly Member[]): Member[] {
  return [...members].sort(
    (a, b) =>
      (PARTY_ORDER[a.party ?? ''] ?? 3) - (PARTY_ORDER[b.party ?? ''] ?? 3) ||
      (a.state ?? '').localeCompare(b.state ?? '') ||
      a.name.localeCompare(b.name),
  );
}

/** How many of each party, in seat order: "D 45 · I 2 · R 53". */
export function tally(members: readonly Member[]): { party: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const m of members) counts.set(m.party ?? '?', (counts.get(m.party ?? '?') ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => (PARTY_ORDER[a[0]] ?? 3) - (PARTY_ORDER[b[0]] ?? 3))
    .map(([party, count]) => ({ party, count }));
}
