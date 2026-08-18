/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { buildTradingPrerequisites } from './tradingPrerequisites';

describe('buildTradingPrerequisites', () => {
  it('blocks desk when Nova API is down', () => {
    const out = buildTradingPrerequisites({
      health: {
        status: 'disconnected',
        latency_ms: 0,
        flag: 'API_DOWN',
        message: 'Backend not running',
      },
      ibkrEnabled: true,
      ibkrConnected: true,
      spendStatus: 'paper_armed',
    });
    expect(out.blockDesk).toBe(true);
    expect(out.autoOverlay).toBe(true);
    expect(out.deskReady).toBe(false);
    expect(out.tradeReady).toBe(false);
    expect(out.items.find((i) => i.id === 'nova_api')?.action).toBe('start_api');
  });

  it('blocks desk when Gateway is disconnected', () => {
    const out = buildTradingPrerequisites({
      health: { status: 'connected', latency_ms: 0, health_source: 'nova_process' },
      ibkrEnabled: true,
      ibkrConnected: false,
      spendStatus: 'paper_armed',
    });
    expect(out.blockDesk).toBe(true);
    expect(out.autoOverlay).toBe(false);
    expect(out.items.find((i) => i.id === 'ibkr_gateway')?.action).toBe('launch_gateway');
  });

  it('offers reconnect (not login) when Gateway port is open but session not READY', () => {
    const out = buildTradingPrerequisites({
      health: { status: 'connected', latency_ms: 0, health_source: 'nova_process' },
      ibkrEnabled: true,
      ibkrConnected: false,
      spendStatus: 'live_armed',
      preferredPortReachable: true,
      ibkrTransportConnected: false,
      disconnectHint: 'live_port_open_but_disconnected',
      sessionReason: 'synchronizing',
    });
    const gw = out.items.find((i) => i.id === 'ibkr_gateway');
    expect(out.blockDesk).toBe(true);
    expect(gw?.ok).toBe(false);
    expect(gw?.action).toBe('reconnect_ibkr');
    expect(gw?.detail).toMatch(/not READY/i);
    expect(gw?.detail.toLowerCase()).toContain('port is open');
    expect(gw?.detail).not.toMatch(/Look at your desktop for 2FA/i);
  });

  it('desk ready but not trade ready when spend locked', () => {
    const out = buildTradingPrerequisites({
      health: { status: 'connected', latency_ms: 0 },
      ibkrEnabled: true,
      ibkrConnected: true,
      spendStatus: 'locked',
    });
    expect(out.blockDesk).toBe(false);
    expect(out.deskReady).toBe(true);
    expect(out.tradeReady).toBe(false);
    expect(out.items.find((i) => i.id === 'orders_armed')?.ok).toBe(false);
  });

  it('trade ready when API + Gateway + spend armed', () => {
    const out = buildTradingPrerequisites({
      health: { status: 'connected', latency_ms: 0 },
      ibkrEnabled: true,
      ibkrConnected: true,
      spendStatus: 'live_armed',
    });
    expect(out.blockDesk).toBe(false);
    expect(out.autoOverlay).toBe(false);
    expect(out.deskReady).toBe(true);
    expect(out.tradeReady).toBe(true);
    expect(out.items.every((i) => i.ok)).toBe(true);
  });

  it('does not block the desk on a client API_WEDGED probe timeout', () => {
    const out = buildTradingPrerequisites({
      health: {
        status: 'disconnected',
        latency_ms: 0,
        flag: 'API_WEDGED',
        message: 'Backend hung (no health response)',
        flag_hint:
          'Port held by a hung process (health timed out) — Nova auto-restarts once in dev, or click Start API.',
      },
      ibkrEnabled: true,
      ibkrConnected: true,
      spendStatus: 'live_armed',
    });
    expect(out.items.find((i) => i.id === 'nova_api')?.ok).toBe(true);
    expect(out.items.find((i) => i.id === 'nova_api')?.action).toBeNull();
    expect(out.blockDesk).toBe(false);
    expect(out.deskReady).toBe(true);
  });

  it('blocks desk when IB loop is wedged even if HTTP health is 5ms', () => {
    const out = buildTradingPrerequisites({
      health: {
        status: 'connected',
        latency_ms: 5,
        ib_loop_lag_ms: { last_ms: 20000, max_ms: 20000, samples: 3, wedged: true },
      },
      ibkrEnabled: true,
      ibkrConnected: true,
      spendStatus: 'paper_armed',
    });
    expect(out.items.find((i) => i.id === 'nova_api')?.ok).toBe(false);
    expect(out.items.find((i) => i.id === 'nova_api')?.action).toBeNull();
    expect(out.blockDesk).toBe(true);
    expect(out.autoOverlay).toBe(true);
    expect(out.deskReady).toBe(false);
  });

  it('offers Use paper Gateway when live is targeted but paper is listening', () => {
    const out = buildTradingPrerequisites({
      health: { status: 'connected', latency_ms: 0, health_source: 'nova_process' },
      ibkrEnabled: true,
      ibkrConnected: false,
      spendStatus: 'live_armed',
      preferredPortReachable: false,
      ibkrTransportConnected: false,
      disconnectHint: 'live_port_refused_paper_listening',
    });
    const gw = out.items.find((i) => i.id === 'ibkr_gateway');
    expect(out.blockDesk).toBe(true);
    expect(gw?.action).toBe('switch_gateway_mode');
    expect(gw?.detail).toMatch(/Paper Gateway is already up/i);
    expect(gw?.detail).not.toMatch(/2FA/i);
  });

  it('never treats Alpaca as a prerequisite id', () => {
    const out = buildTradingPrerequisites({
      health: {
        status: 'connected',
        latency_ms: 999,
        latency_source: 'alpaca_account_http',
      },
      ibkrConnected: true,
      spendStatus: 'paper_armed',
    });
    expect(out.items.some((i) => i.id.includes('alpaca'))).toBe(false);
    expect(out.tradeReady).toBe(true);
  });
});
