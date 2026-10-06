/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { defaultTradeDefaultsPrefs, readTradeDefaultsPrefs, tradeDefaultsStorageKey, writeTradeDefaultsPrefs } from './tradeDefaultsPrefs';
import { TradeSettingsSection } from './TradeSettingsSection';

const confirmed = vi.hoisted(() => ({ venue: 'paper' as DeskVenue | null }));
vi.mock('../ibkr', () => ({ useConfirmedDeskVenue: () => confirmed.venue }));
vi.mock('./PracticeAccountSettings', () => ({ PracticeAccountSettings: () => null }));
vi.mock('./TradeOrderPreferencesForm', () => ({ TradeOrderPreferencesForm: () => <span>Shared confirmation preference</span> }));

describe('Settings stock defaults venue ownership', () => {
  beforeEach(() => { localStorage.clear(); confirmed.venue = 'paper'; });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('follows the confirmed venue while mounted and writes only that venue', () => {
    writeTradeDefaultsPrefs('paper', { ...defaultTradeDefaultsPrefs(), quantity: 7, tif: 'GTC' });
    writeTradeDefaultsPrefs('live', { ...defaultTradeDefaultsPrefs(), quantity: 31 });
    const view = render(<TradeSettingsSection />);
    expect((screen.getByLabelText('Quantity') as HTMLInputElement).value).toBe('7');
    expect(screen.getByRole('heading').textContent).toContain('PAPER');
    confirmed.venue = 'live';
    view.rerender(<TradeSettingsSection />);
    expect((screen.getByLabelText('Quantity') as HTMLInputElement).value).toBe('31');
    expect((screen.getByLabelText('Time-in-Force') as HTMLSelectElement).value).toBe('DAY');
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '43' } });
    expect(readTradeDefaultsPrefs('live').quantity).toBe(43);
    expect(readTradeDefaultsPrefs('paper').quantity).toBe(7);
    act(() => {
      localStorage.setItem(tradeDefaultsStorageKey('live'), JSON.stringify({ schema_version: 2, venue: 'live', prefs: { ...defaultTradeDefaultsPrefs(), quantity: 44 } }));
      window.dispatchEvent(new StorageEvent('storage', { key: tradeDefaultsStorageKey('live'), storageArea: localStorage }));
    });
    expect((screen.getByLabelText('Quantity') as HTMLInputElement).value).toBe('44');
  });

  it('disables edits until the backend confirms a venue', () => {
    confirmed.venue = null;
    render(<TradeSettingsSection />);
    expect(screen.getByRole('status').textContent).toContain('confirm the desk venue');
    expect((screen.getByLabelText('Quantity') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true);
    expect(localStorage.length).toBe(0);
  });

  it('shows save failure and keeps the last saved value', () => {
    render(<TradeSettingsSection />);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '43' } });
    expect(screen.getByRole('alert').textContent).toContain('Could not save trade defaults');
    expect((screen.getByLabelText('Quantity') as HTMLInputElement).value).toBe('100');
  });
});
