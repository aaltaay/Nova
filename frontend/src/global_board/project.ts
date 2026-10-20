/**
 * A market's place on the Global page's map (ADR 060): d3's Natural Earth projection with the parameters the map was
 * drawn with (worldLand.ts; scripts/build-world-land.mjs checks this formula against d3 itself).
 */
import { WORLD_PROJECTION } from './worldLand';

export function project(lon: number, lat: number): [number, number] {
  const l = (lon * Math.PI) / 180;
  const p = (lat * Math.PI) / 180;
  const p2 = p * p;
  const p4 = p2 * p2;
  const x = l * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)));
  const y = p * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)));
  return [WORLD_PROJECTION.tx + WORLD_PROJECTION.scale * x, WORLD_PROJECTION.ty - WORLD_PROJECTION.scale * y];
}
