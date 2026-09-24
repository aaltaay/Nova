/** @vitest-environment jsdom */
/** Click-to-sort on the DAS hotkey table sits over the toolbar's Sort select and selects by id. */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HotkeyRecordsTable } from './HotkeyRecordsTable';
import type { HotkeyCompatStatus, HotkeyRecord, HotkeyRecordAnalysis } from './types';

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function rec(id: string, name: string, label: string): HotkeyRecord {
  return { id, name, key: { label, key: '' }, command: `CMD ${name}` };
}

function analysis(recordId: string, status: HotkeyCompatStatus): HotkeyRecordAnalysis {
  return { recordId, status, evidence: 'das_verified', tokens: [], diagnostics: [] };
}

// The toolbar's Sort select already put these in name order.
const ROWS = [rec('a', 'Alpha', 'F2'), rec('b', 'Bravo', 'F1'), rec('c', 'Charlie', '')];
const ANALYSIS = new Map([
  ['a', analysis('a', 'nova_active')],
  ['b', analysis('b', 'invalid_unsafe')],
]);

const order = () =>
  screen.getAllByRole('row').slice(1).map(r => (r as HTMLTableRowElement).cells[0].textContent);
const header = (name: string) => screen.getByRole('columnheader', { name });

describe('HotkeyRecordsTable sorting', () => {
  it('sorts by key, keeps an unbound key last, and returns to the select order', () => {
    const onSelect = vi.fn();
    render(<HotkeyRecordsTable rows={ROWS} selectedId={null} analysisById={ANALYSIS} onSelect={onSelect} />);
    act(() => fireEvent.click(header('KEY')));
    expect(order()).toEqual(['Bravo', 'Alpha', 'Charlie']);
    act(() => fireEvent.click(header('KEY')));
    expect(order()).toEqual(['Alpha', 'Bravo', 'Charlie']);
    act(() => fireEvent.click(header('KEY')));
    expect(order()).toEqual(['Alpha', 'Bravo', 'Charlie']);
    expect(header('KEY').getAttribute('aria-sort')).toBe('none');
  });

  it('sorts compatibility by its label and still selects the clicked row by id', () => {
    const onSelect = vi.fn();
    render(<HotkeyRecordsTable rows={ROWS} selectedId={null} analysisById={ANALYSIS} onSelect={onSelect} />);
    act(() => fireEvent.click(header('Compatibility')));
    expect(order()).toEqual(['Bravo', 'Alpha', 'Charlie']);
    act(() => fireEvent.click(screen.getByText('Bravo')));
    expect(onSelect).toHaveBeenCalledWith('b');
  });
});
