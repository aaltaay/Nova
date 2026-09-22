/**
 * @vitest-environment jsdom
 *
 * Settings "Update & Connect" (QA C62, 2026-09-22): a refusal is said, with
 * the backend's own words -- it used to leave the overlay open with nothing.
 */
import { act } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSettingsForm } from './useSettingsForm';

const alertApp = vi.fn();
vi.mock('../ux', () => ({ alertApp: (...args: unknown[]) => alertApp(...args) }));
const novaFetch = vi.fn();
vi.mock('../api/novaFetch', () => ({ novaFetch: (...args: unknown[]) => novaFetch(...args) }));

const onSaved = vi.fn();

function Probe() {
  const form = useSettingsForm(onSaved);
  return (
    <form data-testid="form" onSubmit={(e) => void form.handleConfigUpdate(e)}>
      <button type="submit">save</button>
    </form>
  );
}

async function submit() {
  await act(async () => {
    screen.getByText('save').click();
    for (let i = 0; i < 5; i += 1) await Promise.resolve();
  });
}

beforeEach(() => {
  alertApp.mockReset();
  novaFetch.mockReset();
  onSaved.mockReset();
});

afterEach(cleanup);

describe('useSettingsForm save', () => {
  it('a 422 says what Nova answered, with its detail, and saves nothing', async () => {
    novaFetch.mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: 'base_url must be https' }) });
    render(<Probe />);
    await submit();
    expect(onSaved).not.toHaveBeenCalled();
    expect(alertApp).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Settings not saved',
      message: 'Nova refused the change (HTTP 422): base_url must be https Nothing was saved.',
      tone: 'danger',
    }));
  });

  it('a 500 with no readable body still says it was refused', async () => {
    novaFetch.mockResolvedValue({ ok: false, status: 500, json: async () => { throw new SyntaxError('text'); } });
    render(<Probe />);
    await submit();
    expect(alertApp.mock.calls[0][0].message).toBe('Nova refused the change (HTTP 500). Nothing was saved.');
  });

  it('a save that works stays quiet and reports the save', async () => {
    novaFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ data_feed: 'sip' }) });
    render(<Probe />);
    await submit();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(alertApp).not.toHaveBeenCalled();
  });
});
