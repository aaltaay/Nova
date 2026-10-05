/**
 * A CSS animation that never ends may move only what the compositor moves by itself: opacity and transforms.
 * Anything else -- a box-shadow, a background, a colour, a border -- is repainted on the main thread on every
 * frame for as long as it runs. On the desk that repaint is the whole page, re-layered and handed to the
 * compositor again, while it also draws the charts: the Bot card's box-shadow pulse, on all session while the
 * bot is on, was half the main thread's work during a chart drag (measured 2026-10-05, #707). To pulse a
 * colour, put it on a pseudo-element and pulse that element's opacity.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SRC = fileURLToPath(new URL('..', import.meta.url));

/** What the compositor animates without a repaint. */
const COMPOSITED = new Set(['opacity', 'transform', 'translate', 'rotate', 'scale']);

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return name.endsWith('.css') ? [path] : [];
  });
}

const stripComments = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, '');

/** The text between the brace at `open` and its partner. */
function block(text: string, open: number): string {
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    else if (text[i] === '}') {
      depth -= 1;
      if (depth === 0) return text.slice(open + 1, i);
    }
  }
  return text.slice(open + 1);
}

/** Every `@keyframes` name in `texts`, with the properties its frames set. */
function keyframeProps(texts: string[]): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  for (const text of texts) {
    for (const m of text.matchAll(/@keyframes\s+([\w-]+)\s*\{/g)) {
      const body = block(text, (m.index ?? 0) + m[0].length - 1);
      const props = out.get(m[1]) ?? new Set<string>();
      for (const p of body.matchAll(/([a-z-]+)\s*:/g)) props.add(p[1]);
      out.set(m[1], props);
    }
  }
  return out;
}

/** Each `animation:` shorthand that repeats forever, as the keyframes names it uses. */
function infiniteAnimations(text: string, names: Set<string>): string[] {
  const out: string[] = [];
  for (const m of text.matchAll(/(?:^|[;{\s])animation\s*:\s*([^;}]+)/g)) {
    if (!/\binfinite\b/.test(m[1])) continue;
    for (const word of m[1].split(/[\s,]+/)) if (names.has(word)) out.push(word);
  }
  return out;
}

describe('looping animations stay on the compositor', () => {
  it('finds a looping box-shadow animation', () => {
    const css = '.a { animation: glow 1s infinite; } @keyframes glow { 50% { box-shadow: 0 0 4px red; } }';
    const frames = keyframeProps([css]);
    expect(infiniteAnimations(css, new Set(frames.keys()))).toEqual(['glow']);
    expect([...frames.get('glow')!]).toEqual(['box-shadow']);
  });

  it('no stylesheet loops an animation the main thread must repaint', () => {
    const files = cssFiles(SRC).map((path) => ({ path, text: stripComments(readFileSync(path, 'utf8')) }));
    const frames = keyframeProps(files.map((f) => f.text));
    const names = new Set(frames.keys());
    const offenders: string[] = [];
    for (const { path, text } of files) {
      for (const name of infiniteAnimations(text, names)) {
        const painted = [...(frames.get(name) ?? [])].filter((p) => !COMPOSITED.has(p));
        if (painted.length) offenders.push(`${relative(SRC, path)}: ${name} animates ${painted.join(', ')}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
