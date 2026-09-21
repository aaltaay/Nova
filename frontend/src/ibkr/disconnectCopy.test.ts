import { describe, expect, it } from 'vitest';
import {
  EMPTY_IBKR_DISCONNECTED_LIVE,
  EMPTY_IBKR_DISCONNECTED_PAPER,
  GATEWAY_MODE_API_RESTART_HINT,
  STOCK_VIEW_DISCONNECT_HINT_PAPER_LIVE_UP,
  STOCK_VIEW_DISCONNECTED_LABEL,
} from '../constants';
import {
  disconnectHintSwitchTarget,
  emptyIbkrDisconnectedMessage,
  lastKnownAsOfMessage,
  lastKnownBanner,
  stockViewDisconnectLabel,
} from './disconnectCopy';

describe('disconnectCopy', () => {
  it('uses mode-aware empty IBKR disconnected messages', () => {
    expect(emptyIbkrDisconnectedMessage('paper')).toBe(EMPTY_IBKR_DISCONNECTED_PAPER);
    expect(emptyIbkrDisconnectedMessage('live')).toBe(EMPTY_IBKR_DISCONNECTED_LIVE);
    expect(emptyIbkrDisconnectedMessage('paper')).toContain('4002');
    expect(emptyIbkrDisconnectedMessage('live')).toContain('4001');
  });

  it('maps port-mismatch hints to actionable Stock View copy', () => {
    expect(
      stockViewDisconnectLabel({ disconnect_hint: 'paper_port_refused_live_listening' }),
    ).toBe(STOCK_VIEW_DISCONNECT_HINT_PAPER_LIVE_UP);
    expect(stockViewDisconnectLabel({})).toBe(STOCK_VIEW_DISCONNECTED_LABEL);
  });

  it('suggests only live as a switch target -- never the legacy paper Gateway (ADR 020)', () => {
    expect(disconnectHintSwitchTarget('paper_port_refused_live_listening')).toBe('live');
    expect(disconnectHintSwitchTarget('live_port_refused_paper_listening')).toBeNull();
    expect(disconnectHintSwitchTarget('both_ports_unreachable')).toBeNull();
  });

  it('tells the operator the paper Gateway carries no tape instead of offering it', () => {
    const label = stockViewDisconnectLabel({ disconnect_hint: 'live_port_refused_paper_listening' });
    expect(label).toMatch(/legacy/i);
    expect(label).toMatch(/log into the live Gateway/i);
    expect(label).not.toMatch(/switch to Paper/i);
  });

  it('formats last-known disconnect copy without doubling the banner', () => {
    const msg = lastKnownAsOfMessage(1_700_000_000_000);
    expect(msg).toContain('IBKR disconnected -- last known as of');
    expect(lastKnownBanner(msg)).toBe(msg);
    expect(lastKnownBanner('IBKR read failed -- positions (HTTP 503)')).toContain(
      'showing last-known data',
    );
  });

  it('keeps restart-API hint constant for stale gateway-mode 404', () => {
    expect(GATEWAY_MODE_API_RESTART_HINT).toMatch(/Restart Nova API/i);
  });
});
