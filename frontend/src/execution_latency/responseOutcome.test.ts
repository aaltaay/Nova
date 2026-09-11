import { describe, expect, it, vi } from 'vitest';
import { parseTimedExecutionResponse } from './responseOutcome';
import type { BrowserExecutionTiming } from './browserTiming';

function fakeTiming(): BrowserExecutionTiming & { outcomes: boolean[] } {
  const outcomes: boolean[] = [];
  return {
    outcomes,
    complete: (ok: boolean) => {
      outcomes.push(ok);
    },
    clientTimingAtRequest: () => null,
  } as unknown as BrowserExecutionTiming & { outcomes: boolean[] };
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

describe('parseTimedExecutionResponse', () => {
  it('returns a successful body untouched', async () => {
    const timing = fakeTiming();
    const body = await parseTimedExecutionResponse(
      jsonResponse({ ok: true, order_id: 7 }),
      timing,
    );
    expect(body).toEqual({ ok: true, order_id: 7 });
    expect(timing.outcomes).toEqual([true]);
  });

  it('keeps a handled 200 rejection error as-is', async () => {
    const timing = fakeTiming();
    const body = await parseTimedExecutionResponse<{
      ok?: boolean;
      error?: string | null;
    }>(jsonResponse({ ok: false, error: 'OVERSELL' }), timing);
    expect(body.error).toBe('OVERSELL');
    expect(timing.outcomes).toEqual([false]);
  });

  it('promotes a FastAPI string detail to error (D-013)', async () => {
    const timing = fakeTiming();
    const body = await parseTimedExecutionResponse<{
      ok?: boolean;
      error?: string | null;
    }>(jsonResponse({ detail: 'Kill switch tripped' }, 400), timing);
    expect(body.ok).toBe(false);
    expect(body.error).toBe('Kill switch tripped');
    expect(timing.outcomes).toEqual([false]);
  });

  it('promotes a pydantic validation detail list to error', async () => {
    const body = await parseTimedExecutionResponse<{
      ok?: boolean;
      error?: string | null;
    }>(
      jsonResponse(
        { detail: [{ loc: ['body', 'qty'], msg: 'must be > 0' }] },
        422,
      ),
      fakeTiming(),
    );
    expect(body.error).toBe('must be > 0');
  });

  it('marks an HTTP error with no usable detail as not ok', async () => {
    const body = await parseTimedExecutionResponse<{
      ok?: boolean;
      error?: string | null;
    }>(jsonResponse({}, 503), fakeTiming());
    expect(body.ok).toBe(false);
    expect(body.error).toBeUndefined();
  });

  it('does not overwrite an existing error with detail', async () => {
    const body = await parseTimedExecutionResponse<{
      ok?: boolean;
      error?: string | null;
    }>(
      jsonResponse({ ok: false, error: 'KILL_SWITCH', detail: 'ignored' }, 200),
      fakeTiming(),
    );
    expect(body.error).toBe('KILL_SWITCH');
  });

  it('still throws when the body is not JSON', async () => {
    const timing = fakeTiming();
    const response = {
      ok: true,
      status: 200,
      json: () => Promise.reject(new Error('not json')),
    } as unknown as Response;
    await expect(
      parseTimedExecutionResponse(response, timing),
    ).rejects.toThrow('not json');
    expect(timing.outcomes).toEqual([false]);
  });
});

describe('timing outcome is never silently swallowed', () => {
  it('reports transport failure for a 500 with detail', async () => {
    const spy = vi.fn();
    const timing = {
      complete: spy,
      clientTimingAtRequest: () => null,
    } as unknown as BrowserExecutionTiming;
    await parseTimedExecutionResponse(
      jsonResponse({ detail: 'boom' }, 500),
      timing,
    );
    expect(spy).toHaveBeenCalledWith(false);
  });
});
