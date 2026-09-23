/**
 * Windows .ico writer for the app icon (scripts/build-icons.mjs).
 *
 * The classic layout Windows, NSIS and rcedit all read: sizes up to 48 px as
 * 32-bit DIBs (BITMAPINFOHEADER + BGRA rows bottom-up + an AND mask), 256 px
 * as an embedded PNG. Entries are written smallest first.
 */

const ICONDIR_BYTES = 6;
const ICONDIRENTRY_BYTES = 16;
const BITMAPINFOHEADER_BYTES = 40;
/** Largest size stored as a DIB; anything bigger is stored as PNG. */
export const ICO_DIB_MAX_SIZE = 48;

/**
 * One 32-bit DIB image: header, BGRA pixels bottom-up, then a 1-bit AND mask
 * (all zero -- the alpha channel carries transparency).
 * @param {number} size
 * @param {Uint8Array} rgba size*size*4 bytes, top row first
 */
export function dibFromRgba(size, rgba) {
  if (rgba.length !== size * size * 4) {
    throw new Error(`dibFromRgba: expected ${size * size * 4} bytes, got ${rgba.length}`);
  }
  const maskRowBytes = Math.ceil(size / 32) * 4;
  const out = Buffer.alloc(BITMAPINFOHEADER_BYTES + size * size * 4 + maskRowBytes * size);
  out.writeUInt32LE(BITMAPINFOHEADER_BYTES, 0);
  out.writeInt32LE(size, 4);
  out.writeInt32LE(size * 2, 8); // XOR image + AND mask
  out.writeUInt16LE(1, 12); // planes
  out.writeUInt16LE(32, 14); // bits per pixel
  out.writeUInt32LE(size * size * 4 + maskRowBytes * size, 20); // image size
  let o = BITMAPINFOHEADER_BYTES;
  for (let y = size - 1; y >= 0; y -= 1) {
    for (let x = 0; x < size; x += 1) {
      const i = (y * size + x) * 4;
      out[o] = rgba[i + 2];
      out[o + 1] = rgba[i + 1];
      out[o + 2] = rgba[i];
      out[o + 3] = rgba[i + 3];
      o += 4;
    }
  }
  return out;
}

/**
 * @param {{ size: number, data: Buffer }[]} images each `data` a DIB
 *   (dibFromRgba) or a PNG file's bytes
 * @returns {Buffer}
 */
export function encodeIco(images) {
  const sorted = [...images].sort((a, b) => a.size - b.size);
  const header = Buffer.alloc(ICONDIR_BYTES + ICONDIRENTRY_BYTES * sorted.length);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2); // type: icon
  header.writeUInt16LE(sorted.length, 4);
  let offset = header.length;
  sorted.forEach((img, n) => {
    if (img.size < 1 || img.size > 256) throw new Error(`encodeIco: size ${img.size} out of range`);
    const e = ICONDIR_BYTES + n * ICONDIRENTRY_BYTES;
    header[e] = img.size === 256 ? 0 : img.size; // 0 means 256
    header[e + 1] = img.size === 256 ? 0 : img.size;
    header[e + 2] = 0; // palette colours
    header[e + 3] = 0;
    header.writeUInt16LE(1, e + 4); // planes
    header.writeUInt16LE(32, e + 6); // bits per pixel
    header.writeUInt32LE(img.data.length, e + 8);
    header.writeUInt32LE(offset, e + 12);
    offset += img.data.length;
  });
  return Buffer.concat([header, ...sorted.map((img) => img.data)]);
}
