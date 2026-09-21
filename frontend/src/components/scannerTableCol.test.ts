import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { LARGE_CAP_COLUMNS, SCANNER_COLUMNS } from '../constantGroups/scanner_columns';
import { VOLUME_BOOST_COLUMNS } from '../volume_boost/constants';
import {
  SCANNER_COL_ROLE,
  SCANNER_COL_WIDTH,
  SCANNER_TABLE_WRAPPER_CLASS,
  isScannerNumericCol,
  scannerColClass,
  scannerColRole,
} from './scannerTableCol';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, '../styles/scanner-table-cols.css'), 'utf8');

const CATALYST_KEYS = [
  'symbol',
  'previous_close',
  'current_price',
  'gap_percent',
  'volume',
  'catalyst_headline',
  'newest_headline_at',
];

/** Every surface the width lock has to cover (issue #276 acceptance). */
const SHELL_OWNERS: [string, string, string[]][] = [
  ['./ScannerTable.tsx', 'ScannerTable', ['Gappers', 'Gainers', 'Losers', 'After Hours', 'Large Cap']],
  ['./CatalystsTable.tsx', 'CatalystsTable', ['Catalysts']],
  ['../volume_boost/VolumeBoostTable.tsx', 'VolumeBoostTable', ['Volume Boost']],
];

describe('scanner table column width contract', () => {
  it('locks the scanner shell with table-layout:fixed', () => {
    expect(SCANNER_TABLE_WRAPPER_CLASS).toContain('table-wrapper--scanner');
    expect(css).toMatch(/\.table-wrapper--scanner\s+table\s*\{[^}]*table-layout:\s*fixed/s);
  });

  it('reserves identical widths in TS and CSS for live numeric roles', () => {
    for (const [role, width] of Object.entries(SCANNER_COL_WIDTH)) {
      if (role === 'rownum') {
        expect(css).toContain(`.scanner-col--${role}`);
        expect(css).toContain(width);
        continue;
      }
      expect(css).toContain(`.scanner-col--${role}`);
      expect(css).toContain(width);
    }
    expect(css).toMatch(/font-variant-numeric:\s*tabular-nums/);
  });

  it('marks PRICE / CHANGE / GAP % (and Large Cap pct twins) as stable numeric', () => {
    expect(scannerColRole('price')).toBe('price');
    expect(scannerColRole('change_pct')).toBe('pct');
    expect(scannerColRole('gap_percent')).toBe('pct');
    expect(scannerColClass('change_pct')).toContain('scanner-col--pct');
    expect(scannerColClass('gap_percent')).toContain('scanner-col--pct');
    expect(isScannerNumericCol('change_pct')).toBe(true);
    expect(isScannerNumericCol('volume')).toBe(false);

    const liveKeys = [
      ...SCANNER_COLUMNS.map(([key]) => key),
      ...LARGE_CAP_COLUMNS.map(([key]) => key),
      ...VOLUME_BOOST_COLUMNS.map(([key]) => key),
      ...CATALYST_KEYS,
    ];
    for (const key of ['price', 'current_price', 'change_pct', 'gap_percent', 'change_5d_pct']) {
      expect(liveKeys).toContain(key);
      expect(isScannerNumericCol(key)).toBe(true);
    }
  });

  it('applies the shell to every scanner surface, not just Gainers', () => {
    // The acceptance names seven tables. A surface that renders its own
    // wrapper opts out of the width lock silently -- fail loudly instead.
    for (const [file, component, surfaces] of SHELL_OWNERS) {
      const src = readFileSync(resolve(here, file), 'utf8');
      expect(
        src.includes('SCANNER_TABLE_WRAPPER_CLASS'),
        `${component} (${surfaces.join(', ')}) must render the shared scanner shell`,
      ).toBe(true);
      expect(
        src.includes('ScannerColGroup'),
        `${component} must emit the shared colgroup so fixed layout reads reserved widths`,
      ).toBe(true);
      expect(
        src.includes('table-wrapper'),
        `${component} must not hand-roll a table-wrapper class -- use the constant`,
      ).toBe(false);
    }
  });

  it('gives every live scanner column an explicit role', () => {
    // scannerColRole() falls through to 'flex' for unknown keys, which is the
    // right default for prose but means a NEW ticking column would silently go
    // back to auto width. Every shipped column states its role on purpose.
    const declared = new Set(Object.keys(SCANNER_COL_ROLE));
    const shipped = new Set([
      ...SCANNER_COLUMNS.map(([key]) => key),
      ...LARGE_CAP_COLUMNS.map(([key]) => key),
      ...VOLUME_BOOST_COLUMNS.map(([key]) => key),
      ...CATALYST_KEYS,
    ]);
    const undeclared = [...shipped].filter(key => !declared.has(key));
    expect(undeclared, `columns with no width role: ${undeclared.join(', ')}`).toEqual([]);
  });
});
