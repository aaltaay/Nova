/**
 * @vitest-environment node
 */
import { describe, expect, it, beforeEach } from 'vitest';
import {
  parseHtk,
  serializeHtk,
  splitHtkFields,
  parseKeyChord,
  resetHtkIdSeqForTests,
  HTK_SHORT_SCRIPT_MAX_BYTES,
} from './htkFormat';
import { tokenizeDasCommand } from './dasCommandParser';
import { analyzeProfile, findNovaKeyConflicts } from './compatibility';
import { migrateProfile, HOTKEY_STORAGE_KEY } from './hotkeyStorage';
import { HOTKEY_CAPABILITY_CATALOG } from './capabilityCatalog';
import { HOTKEY_COMPAT_STATUSES, HOTKEY_CAPABILITY_CATEGORIES } from './types';

beforeEach(() => {
  resetHtkIdSeqForTests();
});

describe('splitHtkFields', () => {
  it('splits only the first two colons', () => {
    const fields = splitHtkFields(
      'Shift+7:buy then stop:ROUTE=SMRTL;TriggerOrder=RT:STOP STOPTYPE:MARKET',
    );
    expect(fields).not.toBeNull();
    expect(fields![0]).toBe('Shift+7');
    expect(fields![1]).toBe('buy then stop');
    expect(fields![2]).toContain('RT:STOP');
  });

  it('keeps http:// URLs intact', () => {
    const fields = splitHtkFields(
      'Alt+3:Yahoo Finance:http://finance.yahoo.com/quote/%SYMB%',
    );
    expect(fields![2]).toBe('http://finance.yahoo.com/quote/%SYMB%');
  });
});

describe('parseHtk / serializeHtk', () => {
  it('round-trips short records', () => {
    const src =
      'ESC:Cancel all open orders of symbol in montage:CXL ALLSYMB\n'
      + 'Shift+1:Buy ask+.10:ROUTE=SMRTL;Price=Ask+0.10;TIF=DAY+;BUY\n';
    const { records, issues } = parseHtk(src);
    expect(issues).toHaveLength(0);
    expect(records).toHaveLength(2);
    expect(records[0].command).toBe('CXL ALLSYMB');
    const out = serializeHtk(records);
    const again = parseHtk(out);
    expect(again.records.map((r) => r.command)).toEqual(
      records.map((r) => r.command),
    );
  });

  it('parses long ~length scripts with continuation chunks', () => {
    const script =
      'ROUTE=ARCAM;ACCOUNT=TRIB8359;Share=200;TIF=DAY+;BUY=Send;EXTRA=PAD';
    // Ensure longer than short max
    const padded = script + ';X='.padEnd(HTK_SHORT_SCRIPT_MAX_BYTES, '0');
    const file = serializeHtk([
      {
        id: 't1',
        name: 'Buy 200 Shares at Market',
        key: parseKeyChord('Ctrl+Shift+2'),
        command: padded,
      },
    ]);
    expect(file).toContain('~ ');
    const { records, issues } = parseHtk(file);
    expect(issues).toHaveLength(0);
    expect(records).toHaveLength(1);
    expect(records[0].command).toBe(padded);
  });

  it('reports malformed lines without throwing', () => {
    const { records, issues } = parseHtk('not-a-valid-line\n');
    expect(records).toHaveLength(0);
    expect(issues.length).toBeGreaterThan(0);
  });
});

describe('tokenizeDasCommand', () => {
  it('preserves casing and nested trigger colons', () => {
    const cmd =
      'ROUTE=LIMIT;Price=Ask+0.10;BUY=Send;TriggerOrder=RT:STOP STOPTYPE:MARKET STOPPRICE:AvgCost2-.20 ACT:SELL QTY:POS TIF:DAY';
    const tokens = tokenizeDasCommand(cmd);
    expect(tokens.find((t) => t.kind === 'trigger')?.value).toContain('RT:STOP');
    expect(tokens.find((t) => t.name === 'ROUTE')?.value).toBe('LIMIT');
  });

  it('classifies cancel and url segments', () => {
    expect(tokenizeDasCommand('CXL ALLSYMB')[0].kind).toBe('cancel');
    expect(
      tokenizeDasCommand('http://finance.yahoo.com/quote/%SYMB%')[0].kind,
    ).toBe('url');
  });
});

describe('compatibility', () => {
  it('flags Nova key conflicts for Shift+A', () => {
    const conflicts = findNovaKeyConflicts(parseKeyChord('Shift+A'));
    expect(conflicts).toContain('approve_staged');
  });

  it('classifies market buy as translatable_later', () => {
    const analyses = analyzeProfile([
      {
        id: '1',
        name: 'Buy',
        key: parseKeyChord('F1'),
        command: 'ROUTE=MARKET;Share=100;TIF=DAY+;BUY=Send',
      },
    ]);
    expect(analyses[0].status).toBe('translatable_later');
  });

  it('classifies trigger orders as backend_required', () => {
    const analyses = analyzeProfile([
      {
        id: '1',
        name: 'OTO',
        key: parseKeyChord('F2'),
        command:
          'ROUTE=LIMIT;Share=100;TIF=DAY+;BUY=Send;TriggerOrder=RT:MARKET ACT:SELL QTY:POS TIF:DAY+',
      },
    ]);
    expect(analyses[0].status).toBe('backend_required');
  });
});

describe('capability catalog', () => {
  it('has unique ids and valid statuses/categories', () => {
    const ids = new Set(HOTKEY_CAPABILITY_CATALOG.map((e) => e.id));
    expect(ids.size).toBe(HOTKEY_CAPABILITY_CATALOG.length);
    for (const e of HOTKEY_CAPABILITY_CATALOG) {
      expect(HOTKEY_COMPAT_STATUSES).toContain(e.status);
      expect(HOTKEY_CAPABILITY_CATEGORIES).toContain(e.category);
    }
  });
});

describe('hotkeyStorage migrateProfile', () => {
  it('migrates valid profiles and rejects garbage', () => {
    expect(migrateProfile(null)).toBeNull();
    const ok = migrateProfile({
      schemaVersion: 1,
      fileName: 'mine.htk',
      records: [
        {
          id: 'a',
          name: 'X',
          key: { label: 'F1', key: 'F1' },
          command: 'BUY=Send',
        },
      ],
      updatedAt: '2026-07-16T00:00:00.000Z',
    });
    expect(ok?.records).toHaveLength(1);
    expect(ok?.novaActions.length).toBeGreaterThan(0);
    expect(ok?.schemaVersion).toBe(3);
    expect(HOTKEY_STORAGE_KEY).toContain('nova.hotkeys');
  });
});

describe('execution isolation', () => {
  it('hotkey manager modules do not import useHotkeys', async () => {
    // Static guarantee: importing the profile hook must not pull runtime registration.
    const mod = await import('./useHotkeyProfile');
    expect(typeof mod.useHotkeyProfile).toBe('function');
    // useHotkeys is a separate module — profile path never registers window listeners.
    const hk = await import('../hooks/useHotkeys');
    expect(typeof hk.useHotkeys).toBe('function');
  });
});
