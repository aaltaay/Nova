import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
// @ts-expect-error -- plain .mjs build helper, no type declarations
import { dibFromRgba, encodeIco } from './icoEncode.mjs';

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function readEntries(ico: Buffer) {
  const count = ico.readUInt16LE(4);
  return Array.from({ length: count }, (_, n) => {
    const e = 6 + n * 16;
    return {
      size: ico[e] === 0 ? 256 : ico[e],
      bytes: ico.readUInt32LE(e + 8),
      offset: ico.readUInt32LE(e + 12),
    };
  });
}

describe('icoEncode', () => {
  it('writes a 32-bit DIB bottom-up in BGRA with an empty AND mask', () => {
    // 2x2: top row red, green; bottom row blue, transparent
    const rgba = Uint8Array.from([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 0, 0, 0, 0]);
    const dib = dibFromRgba(2, rgba);
    expect(dib.readUInt32LE(0)).toBe(40);
    expect(dib.readInt32LE(8)).toBe(4); // height doubled for the mask
    expect(dib.readUInt16LE(14)).toBe(32);
    // first stored row is the bottom one: blue, then transparent
    expect([...dib.subarray(40, 48)]).toEqual([255, 0, 0, 255, 0, 0, 0, 0]);
    // then the top row: red, green
    expect([...dib.subarray(48, 56)]).toEqual([0, 0, 255, 255, 0, 255, 0, 255]);
    expect(dib.length).toBe(40 + 16 + 4 * 2);
  });

  it('rejects pixel data of the wrong length', () => {
    expect(() => dibFromRgba(2, new Uint8Array(4))).toThrow(/expected 16 bytes/);
  });

  it('indexes entries smallest first with offsets into the file, 256 stored as 0', () => {
    const png = Buffer.concat([PNG_SIGNATURE, Buffer.alloc(4)]);
    const dib = dibFromRgba(1, Uint8Array.from([1, 2, 3, 4]));
    const ico = encodeIco([
      { size: 256, data: png },
      { size: 1, data: dib },
    ]);
    expect(ico.readUInt16LE(2)).toBe(1);
    const entries = readEntries(ico);
    expect(entries.map((e) => e.size)).toEqual([1, 256]);
    expect(ico[6 + 16]).toBe(0);
    expect(entries[0].offset).toBe(6 + 2 * 16);
    expect(ico.subarray(entries[1].offset, entries[1].offset + 8)).toEqual(PNG_SIGNATURE);
    expect(entries[1].offset + entries[1].bytes).toBe(ico.length);
  });

  it('the committed app icon carries every size the build writes', () => {
    const ico = fs.readFileSync(path.join(__dirname, '..', 'electron', 'build', 'icon.ico'));
    expect(readEntries(ico).map((e) => e.size)).toEqual([16, 20, 24, 32, 40, 48, 64, 128, 256]);
  });
});
