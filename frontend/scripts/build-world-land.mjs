/**
 * Draws the world boards' map once (the Global and Forex pages, ADR 060, 061) into src/world_board/worldLand.ts.
 *
 * Land: Natural Earth 1:110m (public domain) through world-atlas 2.0.2's countries-110m, Antarctica left out and the
 * countries merged into one outline, in d3's Natural Earth projection fitted to WORLD_VIEW. The page projects each
 * market's city with the same parameters (src/world_board/project.ts), checked here against d3 itself.
 *
 * Not part of the build: the asset is committed. To draw it again,
 *   npm i --no-save --prefix <dir> world-atlas@2.0.2 topojson-client@3.1.0 d3-geo@3.1.0
 *   node scripts/build-world-land.mjs <dir>/node_modules
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const modules = process.argv[2];
if (!modules) {
  console.error('usage: node scripts/build-world-land.mjs <node_modules with world-atlas, topojson-client, d3-geo>');
  process.exit(2);
}
const req = createRequire(path.join(path.resolve(modules), 'noop.js'));
const topojson = req('topojson-client');
const { geoNaturalEarth1, geoPath } = await import(req.resolve('d3-geo'));
const world = JSON.parse(readFileSync(req.resolve('world-atlas/countries-110m.json'), 'utf8'));

const WIDTH = 1000;
const HEIGHT = 460;
const PAD = 6;
const geoms = world.objects.countries.geometries.filter((g) => g.id !== '010');
const land = topojson.merge(world, geoms);
const projection = geoNaturalEarth1().fitExtent([[PAD, PAD], [WIDTH - PAD, HEIGHT - PAD]], land);
const draw = geoPath(projection).digits(1);
const d = draw(land);
const scale = projection.scale();
const [tx, ty] = projection.translate();

// The page's own projection (project.ts) must land where d3 does.
function raw(lon, lat) {
  const l = (lon * Math.PI) / 180;
  const p = (lat * Math.PI) / 180;
  const p2 = p * p;
  const p4 = p2 * p2;
  return [
    l * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4))),
    p * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4))),
  ];
}
for (const [lon, lat] of [[139.77, 35.68], [-74.01, 40.71], [-46.63, -23.55], [151.21, -33.87], [0, 0]]) {
  const [x, y] = raw(lon, lat);
  const mine = [tx + scale * x, ty - scale * y];
  const theirs = projection([lon, lat]);
  if (Math.abs(mine[0] - theirs[0]) > 0.01 || Math.abs(mine[1] - theirs[1]) > 0.01) {
    throw new Error(`projection mismatch at ${lon},${lat}: ${mine} vs ${theirs}`);
  }
}

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, '..', 'src', 'world_board', 'worldLand.ts');
writeFileSync(out, `/**
 * The world boards' map (the Global and Forex pages, ADR 060, 061), drawn once by scripts/build-world-land.mjs --
 * do not edit by hand.
 * Natural Earth 1:110m land (public domain) through world-atlas 2.0.2, Antarctica left out, in d3's Natural Earth
 * projection fitted to WORLD_VIEW; project.ts places each market or currency with
 * WORLD_PROJECTION.
 */
export const WORLD_VIEW = { width: ${WIDTH}, height: ${HEIGHT} } as const;
export const WORLD_PROJECTION = { scale: ${scale.toFixed(6)}, tx: ${tx.toFixed(6)}, ty: ${ty.toFixed(6)} } as const;
export const WORLD_LAND_PATH =
  '${d}';
`);
console.log(`wrote ${out}: ${d.length} characters of path`);
