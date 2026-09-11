/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import {
  apiProcessOk,
  deskChipTone,
  deskConnectionLabel,
} from './headerConnectionStatusModel';

describe('deskConnectionLabel', () => {
  it('API-down wins over Gateway offline', () => {
    expect(
      deskConnectionLabel({
        apiOk: false,
        connected: false,
        delayed: false,
      }),
    ).toBe('API down');
  });

  it('shows Gateway offline when API is up', () => {
    expect(
      deskConnectionLabel({
        apiOk: true,
        connected: false,
        delayed: false,
      }),
    ).toBe('offline');
  });

  it('shows delayed when both sides are up but feed is delayed', () => {
    expect(
      deskConnectionLabel({
        apiOk: true,
        connected: true,
        delayed: true,
      }),
    ).toBe('delayed');
  });

  it('shows up when API and Gateway are healthy', () => {
    expect(
      deskConnectionLabel({
        apiOk: true,
        connected: true,
        delayed: false,
      }),
    ).toBe('up');
  });

  it('marks the chip stale after missed IBKR status polls', () => {
    expect(
      deskConnectionLabel({
        apiOk: true,
        connected: true,
        delayed: false,
        stale: true,
      }),
    ).toBe('stale');
  });
});

describe('apiProcessOk', () => {
  it('treats client API_WEDGED as still up', () => {
    expect(
      apiProcessOk({
        status: 'disconnected',
        latency_ms: 0,
        flag: 'API_WEDGED',
      }),
    ).toBe(true);
  });

  it('treats API_DOWN as down', () => {
    expect(
      apiProcessOk({
        status: 'disconnected',
        latency_ms: 0,
        flag: 'API_DOWN',
      }),
    ).toBe(false);
  });
});

describe('deskChipTone', () => {
  it('is bad when API is down even if Gateway tone is ok', () => {
    expect(deskChipTone({ apiOk: false, gatewayTone: 'ok' })).toBe('bad');
  });
});
