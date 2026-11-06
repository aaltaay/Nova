/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReviewSymbolButton } from './ReviewSymbolButton';
import { openInNova } from './openInNova';

describe('openInNova', () => {
  it('reads the same-origin token and posts the symbol, date and as_of', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ token: 'tok' }) })
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => ({ chat_message: 'Opened IMCC in Nova Sim on 2026-09-18 at 10:00:00 ET, paused.' }),
      });
    const result = await openInNova(
      { symbol: 'IMCC', date: '2026-09-18', asOf: '10:00' },
      fetchImpl as unknown as typeof fetch,
    );
    expect(result.ok).toBe(true);
    expect(result.message).toContain('paused');
    expect(fetchImpl).toHaveBeenNthCalledWith(1, '/api/review/open-token');
    const init = fetchImpl.mock.calls[1][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['X-Nova-Open-Token']).toBe('tok');
    expect(init.body).toBe(JSON.stringify({ symbol: 'IMCC', date: '2026-09-18', as_of: '10:00' }));
    expect(JSON.stringify(init.headers)).not.toContain('X-Nova-Api-Key');
  });

  it('shows the desk-not-running text when the token request fails', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ error: "Nova's desk is not running. Start it with scripts/windows/Run Nova Desktop.bat, then ask again." }),
    });
    const result = await openInNova(
      { symbol: 'IMCC', date: '2026-09-18', asOf: '10:00' },
      fetchImpl as unknown as typeof fetch,
    );
    expect(result.ok).toBe(false);
    expect(result.message).toContain('Run Nova Desktop.bat');
  });
});

describe('ReviewSymbolButton', () => {
  it('uses the symbol name as the button and shows the answer inline', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ token: 'tok' }) })
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => ({ chat_message: 'Opened IMCC in Nova Sim on 2026-09-18 at 10:00:00 ET, paused.' }),
      });
    vi.stubGlobal('fetch', fetchImpl);
    render(<ReviewSymbolButton symbol="IMCC" date="2026-09-18" asOf="10:00" />);
    fireEvent.click(screen.getByRole('button', { name: 'Open IMCC in Nova' }));
    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('paused');
    vi.unstubAllGlobals();
  });
});
