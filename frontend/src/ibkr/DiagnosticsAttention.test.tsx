/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DiagnosticsAttention, attentionRows } from './DiagnosticsAttention';
import type { DiagRow } from './diagnosticsTypes';

afterEach(cleanup);

function row(id: string, state: string, extra: Partial<DiagRow> = {}): DiagRow {
  return {
    id, group: 'gateway', title: `Title ${id}`, state, detail: `detail ${id}`, cause: `cause ${id}`,
    fix: `fix ${id}`, since: null, action: null, evidence: null, ...extra,
  };
}

const rows: DiagRow[] = [
  row('api', 'ok'),
  row('last_error', 'warn'),
  row('revision', 'unknown'),
  row('recorder', 'off'),
  row('session', 'fail', { action: { kind: 'reconnect_ibkr', label: 'Reconnect' } }),
  row('stalls', 'warn'),
];

describe('attentionRows', () => {
  it('keeps fail, warn and unknown -- worst first, API order within a state -- and drops ok and off', () => {
    expect(attentionRows(rows).map((r) => r.id)).toEqual(['session', 'last_error', 'stalls', 'revision']);
  });
});

describe('DiagnosticsAttention', () => {
  it('lists each row with its full detail and fix, and its action when the desk has one', () => {
    const reconnect = vi.fn();
    render(<DiagnosticsAttention rows={attentionRows(rows)} actions={{ reconnect_ibkr: reconnect }} />);
    const box = screen.getByTestId('diag-attention');
    expect(box.className).toContain('diag-attn--fail');
    expect(box.textContent).toContain('Needs attention');
    const warn = screen.getByTestId('diag-attention-last_error');
    expect(warn.dataset.state).toBe('warn');
    expect(warn.textContent).toContain('detail last_error');
    expect(warn.textContent).toContain('Fix: fix last_error');
    expect(screen.queryByTestId('diag-attention-action-last_error')).toBeNull();
    fireEvent.click(screen.getByTestId('diag-attention-action-session'));
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('renders nothing when every row is OK or off', () => {
    const { container } = render(
      <DiagnosticsAttention rows={attentionRows([row('api', 'ok'), row('recorder', 'off')])} actions={{}} />,
    );
    expect(container.innerHTML).toBe('');
  });
});
