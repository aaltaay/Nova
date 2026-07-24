import { beforeEach, describe, expect, it, vi } from 'vitest';
import { novaFetch } from '../api/novaFetch';
import type { BrowserExecutionTiming } from '../execution_latency';
import { alertApp } from '../ux';
import {
  cancelIbkrOrder,
  cancelIbkrOrderWithFeedback,
} from './cancelOrder';
import {
  cancelAllOrdersForSymbol,
  placeIbkrOrder,
} from './placeOrder';

vi.mock('../api/novaFetch', () => ({
  novaFetch: vi.fn(),
}));

vi.mock('../ux', () => ({
  alertApp: vi.fn(),
}));

function timing(): BrowserExecutionTiming {
  return {
    clientTimingAtRequest: vi.fn(() => ({
      action_wall_ms: 1_000,
      action_performance_ms: 10,
      request_wall_ms: 1_020,
      request_performance_ms: 30,
    })),
    complete: vi.fn(),
  };
}

describe('IBKR client timing contract', () => {
  beforeEach(() => {
    vi.mocked(novaFetch).mockReset();
    vi.mocked(alertApp).mockReset();
  });

  it('sends paired client timing and reference price on place', async () => {
    vi.mocked(novaFetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: true, order_id: 7, error: null }), {
        status: 200,
      }),
    );
    const span = timing();

    await placeIbkrOrder(
      {
        symbol: 'AAPL',
        side: 'BUY',
        qty: 1,
        order_type: 'MKT',
        outside_rth: false,
      },
      'test-idempotency',
      { timing: span, referencePrice: 10.25 },
    );

    const init = vi.mocked(novaFetch).mock.calls[0][1]!;
    const body = JSON.parse(String(init.body));
    expect(body.reference_price).toBe(10.25);
    expect(body.client_timing).toEqual({
      action_wall_ms: 1_000,
      action_performance_ms: 10,
      request_wall_ms: 1_020,
      request_performance_ms: 30,
    });
    expect(span.complete).toHaveBeenCalledWith(true);
  });

  it('sends equivalent X-Nova timing headers on cancel', async () => {
    vi.mocked(novaFetch).mockResolvedValue(new Response('{}', { status: 200 }));
    const span = timing();

    await cancelIbkrOrder(42, span);

    const init = vi.mocked(novaFetch).mock.calls[0][1]!;
    const headers = new Headers(init.headers);
    expect(headers.get('X-Nova-Action-Wall-Ms')).toBe('1000');
    expect(headers.get('X-Nova-Request-Performance-Ms')).toBe('30');
    expect(span.complete).toHaveBeenCalledWith(true);
  });

  it('records HTTP 200 place rejection as a failed browser outcome', async () => {
    vi.mocked(novaFetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: false, order_id: null, error: 'Risk rejected' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const span = timing();

    const result = await placeIbkrOrder(
      {
        symbol: 'AAPL',
        side: 'BUY',
        qty: 1,
        order_type: 'MKT',
        outside_rth: false,
      },
      'rejected-place',
      { timing: span },
    );

    expect(result.ok).toBe(false);
    expect(span.complete).toHaveBeenCalledWith(false);
  });

  it('records HTTP 200 cancel rejection as a failed browser outcome', async () => {
    vi.mocked(novaFetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: false, error: 'Already filled' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const span = timing();

    const result = await cancelIbkrOrder(42, span);

    expect(result.ok).toBe(false);
    expect(result.error).toBe('Already filled');
    expect(span.complete).toHaveBeenCalledWith(false);
  });

  it('records HTTP 200 cancel-all rejection as a failed browser outcome', async () => {
    vi.mocked(novaFetch).mockResolvedValue(
      new Response(JSON.stringify({
        ok: false,
        cancelled: [],
        failed: [{ order_id: 42, error: 'Rejected' }],
        error: 'Cancel-all failed',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const span = timing();

    const result = await cancelAllOrdersForSymbol('AAPL', span);

    expect(result.ok).toBe(false);
    expect(span.complete).toHaveBeenCalledWith(false);
  });

  it('requires transport and body success and records network failure', async () => {
    vi.mocked(novaFetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, error: null }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const transportSpan = timing();
    const transportResult = await cancelIbkrOrder(42, transportSpan);
    expect(transportResult.ok).toBe(false);
    expect(transportSpan.complete).toHaveBeenCalledWith(false);

    vi.mocked(novaFetch).mockRejectedValueOnce(new Error('Network down'));
    const networkSpan = timing();
    await expect(cancelIbkrOrder(42, networkSpan)).rejects.toThrow('Network down');
    expect(networkSpan.complete).toHaveBeenCalledWith(false);
  });

  it('shows backend cancel rejection and refreshes polling state', async () => {
    vi.mocked(novaFetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: false, error: 'Order already filled' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.mocked(alertApp).mockResolvedValue(undefined);
    const refresh = vi.fn();

    const ok = await cancelIbkrOrderWithFeedback(42, refresh);

    expect(ok).toBe(false);
    expect(alertApp).toHaveBeenCalledWith({
      title: 'Cancel failed',
      message: 'Order already filled',
      tone: 'danger',
    });
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('shows network cancel failure and still refreshes polling state', async () => {
    vi.mocked(novaFetch).mockRejectedValue(new Error('Gateway unavailable'));
    vi.mocked(alertApp).mockResolvedValue(undefined);
    const refresh = vi.fn();

    const ok = await cancelIbkrOrderWithFeedback(42, refresh);

    expect(ok).toBe(false);
    expect(alertApp).toHaveBeenCalledWith({
      title: 'Cancel failed',
      message: 'Gateway unavailable',
      tone: 'danger',
    });
    expect(refresh).toHaveBeenCalledOnce();
  });
});
