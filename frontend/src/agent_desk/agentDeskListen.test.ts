/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AgentDeskUnavailable, fetchNextCommand, reportCommand, type AgentCommand } from './agentDeskApi';
import { AGENT_DESK_RETRY_MS, AGENT_DESK_UNAVAILABLE_RETRY_MS } from './agentDeskConstants';
import { listenForAgentCommands } from './agentDeskListen';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

afterEach(() => vi.restoreAllMocks());

const COMMAND: AgentCommand = { id: 'c1', kind: 'unreadable', status: 'running', error: 'x' };

describe('listenForAgentCommands', () => {
  it('backs off rarely from an API without the endpoints, runs a command, and stops on abort', async () => {
    const controller = new AbortController();
    const waits: number[] = [];
    let calls = 0;
    const next = vi.fn(async () => {
      calls += 1;
      if (calls === 1) throw new AgentDeskUnavailable('404');
      if (calls === 2) throw new Error('network');
      if (calls === 3) return COMMAND;
      controller.abort();
      return null;
    });
    const run = vi.fn(async () => {});
    await listenForAgentCommands(controller.signal, {
      openTab: vi.fn(), notice: vi.fn(), next, run, sleep: async ms => { waits.push(ms); },
    });
    expect(waits).toEqual([AGENT_DESK_UNAVAILABLE_RETRY_MS, AGENT_DESK_RETRY_MS * 2]);
    expect(run).toHaveBeenCalledOnce();
    expect(run.mock.calls[0][0]).toBe(COMMAND);
  });

  it('a command that throws never ends the loop', async () => {
    const controller = new AbortController();
    let calls = 0;
    const next = vi.fn(async () => { calls += 1; if (calls > 1) controller.abort(); return calls === 1 ? COMMAND : null; });
    const run = vi.fn(async () => { throw new Error('report failed'); });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    await listenForAgentCommands(controller.signal, { openTab: vi.fn(), notice: vi.fn(), next, run });
    expect(next).toHaveBeenCalledTimes(2);
  });
});

describe('the desk requests', () => {
  it('the long poll names this window and an API without the endpoints is unavailable', async () => {
    mocks.fetch.mockReset().mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({}) });
    await expect(fetchNextCommand()).rejects.toBeInstanceOf(AgentDeskUnavailable);
    expect(String(mocks.fetch.mock.calls[0][0])).toContain('/api/agent/desk/next?wait=25&window_id=main');
    mocks.fetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ command: null }) });
    expect(await fetchNextCommand()).toBeNull();
  });

  it('a report answers the command status after it', async () => {
    mocks.fetch.mockReset().mockResolvedValueOnce({ ok: true, status: 200,
      json: async () => ({ command: { id: 'c1', status: 'cancelled' } }) });
    expect(await reportCommand('c1', { status: 'running', step: 'load', text: '40%' })).toBe('cancelled');
    const [url, init] = mocks.fetch.mock.calls[0];
    expect(String(url)).toContain('/api/agent/desk/commands/c1');
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ status: 'running', step: 'load', text: '40%' });
  });
});
