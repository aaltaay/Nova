/**
 * Build Nova's app icon from its SVG sources.
 * Usage: npm run icons
 *
 *   electron/build/icon-small.svg -> 16-48 px   (window, taskbar, Explorer lists)
 *   electron/build/icon.svg       -> 64-256 px  (desktop, Start, installer)
 *
 * Writes electron/build/icon.ico -- electron-builder's app and installer icon,
 * and the desktop window's icon (electron/main.mjs) -- and copies the small
 * source to public/favicon.svg for the browser tab. Each size is rasterised
 * from the vector in Chromium (Playwright), so nothing is scaled down from a
 * big bitmap. The outputs are committed; run this only after editing an SVG.
 */
import { copyFileSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { ICO_DIB_MAX_SIZE, dibFromRgba, encodeIco } from './icoEncode.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, '..');
const buildDir = path.join(frontendDir, 'electron', 'build');
const SMALL_SVG = path.join(buildDir, 'icon-small.svg');
const LARGE_SVG = path.join(buildDir, 'icon.svg');
const ICO_OUT = path.join(buildDir, 'icon.ico');
const FAVICON_OUT = path.join(frontendDir, 'public', 'favicon.svg');

const SMALL_SIZES = [16, 20, 24, 32, 40, 48];
const LARGE_SIZES = [64, 128, 256];

function svgDataUrl(file) {
  return `data:image/svg+xml;base64,${readFileSync(file).toString('base64')}`;
}

/** Rasterise one SVG at one size; returns RGBA pixels and the PNG bytes. */
async function render(page, file, size) {
  const { rgba, png } = await page.evaluate(
    async ({ url, size: s }) => {
      const img = new Image();
      img.src = url;
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = s;
      canvas.height = s;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, s, s);
      const pixels = ctx.getImageData(0, 0, s, s).data;
      return { rgba: Array.from(pixels), png: canvas.toDataURL('image/png').split(',')[1] };
    },
    { url: svgDataUrl(file), size },
  );
  return { rgba: Uint8Array.from(rgba), png: Buffer.from(png, 'base64') };
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const images = [];
  for (const size of SMALL_SIZES) {
    const { rgba, png } = await render(page, SMALL_SVG, size);
    images.push({ size, data: size <= ICO_DIB_MAX_SIZE ? dibFromRgba(size, rgba) : png });
  }
  for (const size of LARGE_SIZES) {
    const { rgba, png } = await render(page, LARGE_SVG, size);
    images.push({ size, data: size <= ICO_DIB_MAX_SIZE ? dibFromRgba(size, rgba) : png });
  }
  writeFileSync(ICO_OUT, encodeIco(images));
  copyFileSync(SMALL_SVG, FAVICON_OUT);
  console.log(`wrote ${path.relative(frontendDir, ICO_OUT)} (${images.map((i) => i.size).join(', ')} px)`);
  console.log(`wrote ${path.relative(frontendDir, FAVICON_OUT)}`);
} finally {
  await browser.close();
}
