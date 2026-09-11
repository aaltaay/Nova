import net from 'node:net';

export const SIDECAR_PORT_FREE_TIMEOUT_MS = 8_000;
export const SIDECAR_PORT_POLL_MS = 150;
export const SIDECAR_PORT_PROBE_MS = 300;

export function probePort(host, port, timeoutMs = SIDECAR_PORT_PROBE_MS) {
  return new Promise((resolve) => {
    const sock = net.connect({ host, port }, () => {
      sock.end();
      resolve(true);
    });
    sock.on('error', () => resolve(false));
    sock.setTimeout(timeoutMs, () => {
      sock.destroy();
      resolve(false);
    });
  });
}

export async function waitUntil(predicate, timeoutMs, intervalMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await predicate()) return true;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return predicate();
}

export async function waitForPortFree(host, port, timeoutMs = SIDECAR_PORT_FREE_TIMEOUT_MS) {
  return waitUntil(
    async () => !(await probePort(host, port)),
    timeoutMs,
    SIDECAR_PORT_POLL_MS,
  );
}
