/**
 * GitHub's release ping (operator ask 2026-10-14): GitHub cannot call the desk, so `Desktop pack`
 * posts each published vNNN to an ntfy.sh topic and the desk keeps a connection open to it. A ping
 * only names a tag; the desk then asks GitHub itself.
 */
import fs from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RELEASE_PING_RETRY_MAX_MS,
  RELEASE_PING_RETRY_MIN_MS,
  RELEASE_PING_SERVER,
  RELEASE_PING_SILENT_MS,
  RELEASE_PING_TOPIC,
  createReleasePing,
  readPingLine,
  releasePingUrl,
} from '../../electron/releasePing.mjs';

const enc = new TextEncoder();

/** One open connection: the test pushes ntfy lines into it, ends it, or lets it go silent. */
function stream(signal?: AbortSignal) {
  const chunks: (string | null)[] = [];
  let wake: (() => void) | null = null;
  const push = (chunk: string | null) => {
    chunks.push(chunk);
    wake?.();
  };
  signal?.addEventListener('abort', () => push(null));
  return {
    push,
    response: {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => {
            while (!chunks.length) await new Promise<void>((resolve) => { wake = resolve; });
            wake = null;
            const next = chunks.shift();
            if (next === null || next === undefined) {
              if (signal?.aborted) throw signal.reason ?? new Error('aborted');
              return { done: true, value: undefined };
            }
            return { done: false, value: enc.encode(next) };
          },
        }),
      },
    },
  };
}

const line = (body: Record<string, unknown>) => `${JSON.stringify(body)}\n`;

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('the stream', () => {
  it('reads a release ping and nothing else as a tag', () => {
    expect(readPingLine('{"id":"a","time":1760000000,"event":"message","topic":"t","message":"v1290"}')).toEqual({
      time: 1760000000,
      tag: 'v1290',
    });
    expect(readPingLine('{"id":"b","time":1760000001,"event":"keepalive","topic":"t"}')).toEqual({ time: 1760000001, tag: '' });
    // A message that is not a release tag is no ping; a line that is not an event is nothing.
    expect(readPingLine('{"id":"c","time":1,"event":"message","message":"rm -rf /"}')?.tag).toBe('');
    expect(readPingLine('not json')).toBeNull();
    expect(readPingLine('')).toBeNull();
    expect(readPingLine('{"message":"v1290"}')).toBeNull();
  });

  it('asks again from the last event read after a drop', () => {
    expect(releasePingUrl(0)).toBe(`${RELEASE_PING_SERVER}/${RELEASE_PING_TOPIC}/json`);
    expect(releasePingUrl(1760000000.5)).toBe(`${RELEASE_PING_SERVER}/${RELEASE_PING_TOPIC}/json?since=1760000000`);
  });

  it('is the topic Desktop pack posts to', () => {
    const workflow = fs.readFileSync(new URL('../../../.github/workflows/desktop-pack.yml', import.meta.url), 'utf8');
    expect(workflow).toContain(`https://ntfy.sh/${RELEASE_PING_TOPIC}"`);
    expect(RELEASE_PING_SERVER).toBe('https://ntfy.sh');
  });
});

describe('the connection', () => {
  function setup() {
    const opened: { url: string; s: ReturnType<typeof stream> }[] = [];
    const fetch = vi.fn(async (url: string, init: { signal?: AbortSignal }) => {
      const s = stream(init.signal);
      opened.push({ url, s });
      return s.response;
    });
    const onRelease = vi.fn();
    const logger = { info: vi.fn(), warn: vi.fn() };
    const ping = createReleasePing({ fetch, onRelease, logger });
    return { ping, fetch, onRelease, logger, opened };
  }

  it('hands every release tag it reads to the desk', async () => {
    const { ping, onRelease, opened, logger } = setup();
    ping.start();
    await vi.advanceTimersByTimeAsync(0);
    opened[0].s.push(line({ id: 'o', time: 100, event: 'open', topic: RELEASE_PING_TOPIC }));
    // Two events in one chunk, the second split across chunks.
    opened[0].s.push(`${line({ id: 'k', time: 101, event: 'keepalive' })}{"id":"m","time":102,"ev`);
    opened[0].s.push('ent":"message","message":"v1290"}\n');
    await vi.advanceTimersByTimeAsync(0);
    expect(onRelease).toHaveBeenCalledTimes(1);
    expect(onRelease).toHaveBeenCalledWith('v1290');
    expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('listening for release pings'));
    ping.stop();
  });

  it('opens again after a drop, asking for what was posted since', async () => {
    const { ping, opened, logger } = setup();
    ping.start();
    await vi.advanceTimersByTimeAsync(0);
    opened[0].s.push(line({ id: 'o', time: 1760000000, event: 'open' }));
    opened[0].s.push(null); // ntfy closed the connection
    await vi.advanceTimersByTimeAsync(0);
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('release ping connection lost'));
    expect(opened).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(RELEASE_PING_RETRY_MIN_MS);
    expect(opened).toHaveLength(2);
    expect(opened[1].url).toBe(releasePingUrl(1760000000));
    opened[1].s.push(line({ id: 'o2', time: 1760000300, event: 'open' }));
    await vi.advanceTimersByTimeAsync(0);
    expect(logger.info).toHaveBeenCalledWith('release ping connection is back');
    ping.stop();
  });

  it('drops a connection that goes silent past the keepalive', async () => {
    const { ping, opened } = setup();
    ping.start();
    await vi.advanceTimersByTimeAsync(0);
    opened[0].s.push(line({ id: 'o', time: 5, event: 'open' }));
    await vi.advanceTimersByTimeAsync(RELEASE_PING_SILENT_MS + RELEASE_PING_RETRY_MIN_MS);
    expect(opened).toHaveLength(2);
    ping.stop();
  });

  it('backs off to every few minutes while ntfy cannot be reached, and logs the outage once', async () => {
    const fetch = vi.fn(async () => {
      throw new Error('getaddrinfo ENOTFOUND ntfy.sh');
    });
    const logger = { info: vi.fn(), warn: vi.fn() };
    const ping = createReleasePing({ fetch, onRelease: vi.fn(), logger });
    ping.start();
    await vi.advanceTimersByTimeAsync(60 * 60_000);
    // 5 s, 10 s, 20 s ... up to 5 min: about 15 tries in an hour, not 720.
    expect(fetch.mock.calls.length).toBeGreaterThan(5);
    expect(fetch.mock.calls.length).toBeLessThan(60 * 60_000 / RELEASE_PING_RETRY_MAX_MS + 10);
    expect(logger.warn).toHaveBeenCalledTimes(1);
    ping.stop();
  });

  it('stops for good when stopped', async () => {
    const { ping, opened, fetch } = setup();
    ping.start();
    await vi.advanceTimersByTimeAsync(0);
    ping.stop();
    await vi.advanceTimersByTimeAsync(RELEASE_PING_RETRY_MAX_MS * 2);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(opened).toHaveLength(1);
  });
});
