/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DiagnosticsChecklist } from './DiagnosticsChecklist';
import type { DiagnosticsPayload } from './diagnosticsTypes';

afterEach(cleanup);

const payload: DiagnosticsPayload = {
  schema_version: 1,
  generated_at: 1790055173.28,
  groups: [
    { id: 'process', title: 'Process' },
    { id: 'gateway', title: 'Gateway' },
    { id: 'practice', title: 'Practice' },
  ],
  counts: { ok: 1, warn: 1, fail: 1 },
  rows: [
    {
      id: 'process_root', group: 'process', title: 'Repo root the API runs from', state: 'warn',
      detail: 'C:\\Nova\\.claude\\worktrees\\agent-x -- a git worktree, not the main checkout',
      cause: 'This API was started from an agent worktree.', fix: 'Stop this process and start the API from the main repository.',
      since: null, action: { kind: 'reload_backend', label: 'Reload backend' }, evidence: { worktree: true },
    },
    {
      id: 'gateway_session', group: 'gateway', title: 'Nova session', state: 'fail',
      detail: 'port open, session not READY', cause: 'Attach stalled.', fix: 'Reconnect Nova to Gateway.',
      since: 1790055100, action: { kind: 'reconnect_ibkr', label: 'Reconnect' }, evidence: { reason: 'gateway_authenticating' },
    },
    {
      id: 'practice_ledger', group: 'practice', title: 'Paper ledger', state: 'ok',
      detail: 'practice-paper.json schema 2', cause: 'Found.', fix: 'Nothing to do.',
      since: null, action: { kind: 'open_something_unknown', label: 'Unknown action' }, evidence: {},
    },
  ],
};

describe('DiagnosticsChecklist', () => {
  it('groups rows under their group titles with a state per row and the counts', () => {
    render(<DiagnosticsChecklist data={payload} actions={{}} onRefresh={() => {}} copyBundle={async () => ''} />);
    expect(screen.getByTestId('diag-group-process').textContent).toContain('Repo root the API runs from');
    expect(screen.getByTestId('diag-row-process_root').dataset.state).toBe('warn');
    expect(screen.getByTestId('diag-row-gateway_session').dataset.state).toBe('fail');
    expect(screen.getByTestId('diag-counts').textContent).toMatch(/1 Fail.*1 Warn.*1 OK/);
  });

  it('expands a row to its cause, fix and raw evidence', () => {
    render(<DiagnosticsChecklist data={payload} actions={{}} onRefresh={() => {}} copyBundle={async () => ''} />);
    expect(screen.queryByTestId('diag-row-more-process_root')).toBeNull();
    fireEvent.click(screen.getByTestId('diag-row-toggle-process_root'));
    const more = screen.getByTestId('diag-row-more-process_root');
    expect(more.textContent).toContain('started from an agent worktree');
    expect(more.textContent).toContain('start the API from the main repository');
    expect(more.textContent).toContain('"worktree": true');
  });

  it('renders an action only when the desk has a handler for it', () => {
    const reconnect = vi.fn();
    render(
      <DiagnosticsChecklist data={payload} actions={{ reconnect_ibkr: reconnect }} onRefresh={() => {}} copyBundle={async () => ''} />,
    );
    expect(screen.queryByTestId('diag-row-action-process_root')).toBeNull();
    expect(screen.queryByTestId('diag-row-action-practice_ledger')).toBeNull();
    fireEvent.click(screen.getByTestId('diag-row-action-gateway_session'));
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('copies the plain-text bundle, and shows it to select when the clipboard refuses', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const view = render(
      <DiagnosticsChecklist data={payload} actions={{}} onRefresh={() => {}} copyBundle={async () => 'Nova desk diagnostics'} />,
    );
    fireEvent.click(screen.getByTestId('diag-copy'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('Nova desk diagnostics'));
    expect(screen.getByTestId('diag-copy').textContent).toBe('Copied');
    view.unmount();

    writeText.mockRejectedValueOnce(new Error('denied'));
    render(<DiagnosticsChecklist data={payload} actions={{}} onRefresh={() => {}} copyBundle={async () => 'bundle text'} />);
    fireEvent.click(screen.getByTestId('diag-copy'));
    await waitFor(() => expect(screen.getByTestId('diag-copy-failed')).toBeTruthy());
    expect((screen.getByTestId('diag-copy-failed').querySelector('textarea') as HTMLTextAreaElement).value).toBe('bundle text');
  });
});
