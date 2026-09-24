/**
 * The Windows desk composites in software (electron/gpuPolicy.mjs), where a
 * backdrop-filter is recomputed on the CPU every time anything under it
 * repaints -- the Trading prerequisites panel scrolled at a few frames a second
 * over the live desk (2026-09-23). A scrim is a plain translucent background.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SRC = fileURLToPath(new URL('..', import.meta.url));
const SELF = fileURLToPath(import.meta.url);

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(css|tsx?)$/.test(name) && path !== SELF ? [path] : [];
  });
}

const stripComments = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

describe('no backdrop-filter on the desk', () => {
  it('no stylesheet or component blurs what is behind it', () => {
    const offenders = files(SRC).filter((path) =>
      /backdrop-filter\s*:|backdropFilter\s*:|\bbackdrop-blur/.test(stripComments(readFileSync(path, 'utf8'))),
    );
    expect(offenders.map((path) => relative(SRC, path))).toEqual([]);
  });
});
