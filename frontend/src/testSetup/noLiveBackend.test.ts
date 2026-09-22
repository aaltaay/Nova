import { describe, expect, it } from 'vitest';
import { LIVE_BACKEND_REFUSAL } from './noLiveBackend';

describe('tests never reach the live Nova backend', () => {
  it('refuses a fetch to the local API before anything is sent', async () => {
    await expect(fetch('http://127.0.0.1:8000/api/ibkr/status')).rejects.toThrow(LIVE_BACKEND_REFUSAL);
    await expect(fetch('http://localhost:8000/api/health')).rejects.toThrow(LIVE_BACKEND_REFUSAL);
    await expect(fetch('/api/practice/account?venue=paper')).rejects.toThrow(LIVE_BACKEND_REFUSAL);
  });

  it('hands back an inert socket that closes instead of connecting', async () => {
    const socket = new WebSocket('ws://127.0.0.1:8000/ws/scanner');
    const closed = new Promise<void>((resolve) => socket.addEventListener('close', () => resolve()));
    await closed;
    expect(socket.readyState).toBe(WebSocket.CLOSED);
  });
});
