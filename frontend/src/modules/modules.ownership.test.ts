import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { Level2Module } from './Level2Module';
import { TimeSalesModule } from './TimeSalesModule';

const here = dirname(fileURLToPath(import.meta.url));

describe('Level2Module / TimeSalesModule', () => {
  it('exports mountable components that accept only symbol', () => {
    expect(typeof Level2Module).toBe('function');
    expect(typeof TimeSalesModule).toBe('function');
    expect(Level2Module.length).toBe(1);
    expect(TimeSalesModule.length).toBe(1);
  });

  it('each module owns its feed hook (not the sibling)', () => {
    const l2 = readFileSync(join(here, 'Level2Module.tsx'), 'utf8');
    const ts = readFileSync(join(here, 'TimeSalesModule.tsx'), 'utf8');
    expect(l2).toMatch(/DepthLadder/);
    expect(l2).not.toMatch(/TimeSales|useIbkrTape/);
    expect(ts).toMatch(/TimeSalesPanel/);
    expect(ts).not.toMatch(/DepthLadder|useIbkrDepth/);
  });
});
