/**
 * Socket-message and render tallies for this window's performance report
 * (ADR 026). `countSocketMessage` runs on every WebSocket frame and
 * `countRender` on every render of a counted component, so both are one map
 * lookup and an add: a socket's slot is allocated once and zeroed by
 * `takeCounters`, never re-created. New names past the key caps are ignored
 * rather than grown without bound.
 */
import { PERF_MAX_RENDER_KEYS, PERF_MAX_SOCKET_KEYS } from '../constantGroups/perf';

export interface SocketTally {
  messages: number;
  bytes: number;
}

export interface PerfCounters {
  sockets: Record<string, SocketTally>;
  renders: Record<string, number>;
}

const sockets = new Map<string, SocketTally>();
const renders = new Map<string, number>();

/** Size of a WebSocket frame: string length, or an ArrayBuffer / Blob's bytes. */
export function frameBytes(data: unknown): number {
  if (typeof data === 'string') return data.length;
  if (data != null && typeof data === 'object') {
    const sized = data as { byteLength?: number; size?: number };
    return sized.byteLength ?? sized.size ?? 0;
  }
  return 0;
}

export function countSocketMessage(name: string, bytes: number): void {
  let slot = sockets.get(name);
  if (slot === undefined) {
    if (sockets.size >= PERF_MAX_SOCKET_KEYS) return;
    slot = { messages: 0, bytes: 0 };
    sockets.set(name, slot);
  }
  slot.messages += 1;
  slot.bytes += bytes;
}

export function countRender(name: string): void {
  const n = renders.get(name);
  if (n === undefined && renders.size >= PERF_MAX_RENDER_KEYS) return;
  renders.set(name, (n ?? 0) + 1);
}

/** Everything counted since the previous call (quiet sockets left out), then zero. */
export function takeCounters(): PerfCounters {
  const out: PerfCounters = { sockets: {}, renders: {} };
  for (const [name, slot] of sockets) {
    if (slot.messages === 0) continue;
    out.sockets[name] = { messages: slot.messages, bytes: slot.bytes };
    slot.messages = 0;
    slot.bytes = 0;
  }
  for (const [name, n] of renders) out.renders[name] = n;
  renders.clear();
  return out;
}

/** Test helper: forget every name, not only the counts. */
export function resetPerfCountersForTests(): void {
  sockets.clear();
  renders.clear();
}
