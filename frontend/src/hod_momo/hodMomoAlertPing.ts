/**
 * Desk ping when a new HOD Momentum row lands.
 *
 * Banner mute (this module + localStorage) is the SSOT for the look-over ping.
 * `StrategyConfig.audio` / Configure "Audio Alert" is per-strategy Warrior
 * config persisted on the server. It has no play path today and defaults
 * vary (Former Momo off). Wiring the banner to that flag would mute some
 * strategies by default and would not survive as a simple local toggle.
 *
 * Running Up shares the WS stream but is a sibling scanner -- Ahmed's ping
 * is HOD Momo list rows only.
 *
 * Oscillator matches `strategy/novaOsAttention.ts` (short quiet sine, no mp3).
 */
import { HOD_MOMO_RUNNING_UP_STRATEGY_ID } from '../constants';

export const HOD_MOMO_ALERT_SOUND_STORAGE_KEY = 'nova.hodMomo.alertSound';
/** Default ON -- a new HOD row pings until the operator mutes. */
export const HOD_MOMO_ALERT_SOUND_DEFAULT = true;
/** One ping if several new rows land in this window (covers two 150ms flushes). */
export const HOD_MOMO_ALERT_PING_COALESCE_MS = 400;
const PING_FREQ_HZ = 880;
const PING_GAIN = 0.04;
const PING_DECAY_SEC = 0.18;
const PING_STOP_SEC = 0.2;

export type HodAlertPingArrival = {
  id: string;
  ticker: string;
  timestamp: string;
  strategy_id: number;
};

type PingMemory = {
  keys: Set<string>;
  tickers: Set<string>;
};

const memory: PingMemory = {
  keys: new Set(),
  tickers: new Set(),
};

let soundOn = HOD_MOMO_ALERT_SOUND_DEFAULT;
let audioCtx: AudioContext | null = null;
let coalesceTimer: ReturnType<typeof setTimeout> | null = null;
let pendingPing = false;

function readStored(): boolean {
  try {
    const raw = localStorage.getItem(HOD_MOMO_ALERT_SOUND_STORAGE_KEY);
    if (raw == null) return HOD_MOMO_ALERT_SOUND_DEFAULT;
    return raw === '1' || raw === 'true';
  } catch {
    return HOD_MOMO_ALERT_SOUND_DEFAULT;
  }
}

soundOn = readStored();

export function isHodMomoAlertSoundOn(): boolean {
  return soundOn;
}

export function hydrateHodMomoAlertSoundFromStorage(): boolean {
  soundOn = readStored();
  return soundOn;
}

export function setHodMomoAlertSoundOn(next: boolean): void {
  soundOn = next;
  try {
    localStorage.setItem(HOD_MOMO_ALERT_SOUND_STORAGE_KEY, next ? '1' : '0');
  } catch {
    // quota / private mode
  }
  if (next) void resumeAudioCtx();
}

function isRunningUp(strategyId: number): boolean {
  return strategyId === HOD_MOMO_RUNNING_UP_STRATEGY_ID;
}

export function hodAlertPingIdKey(alert: HodAlertPingArrival): string {
  const id = (alert.id || '').trim();
  return id ? `id:${id}` : hodAlertPingSymTimeKey(alert);
}

export function hodAlertPingSymTimeKey(alert: HodAlertPingArrival): string {
  return `sym:${(alert.ticker || '').toUpperCase()}|${alert.timestamp || ''}`;
}

export function ingestHodMomoAlertSnapshot(alerts: HodAlertPingArrival[]): void {
  memory.keys.clear();
  memory.tickers.clear();
  for (const alert of alerts) {
    if (isRunningUp(alert.strategy_id)) continue;
    memory.keys.add(hodAlertPingIdKey(alert));
    memory.keys.add(hodAlertPingSymTimeKey(alert));
    const ticker = (alert.ticker || '').toUpperCase();
    if (ticker) memory.tickers.add(ticker);
  }
}

export function collectHodMomoNewRows(
  arrivals: HodAlertPingArrival[],
): HodAlertPingArrival[] {
  const newRows: HodAlertPingArrival[] = [];
  for (const alert of arrivals) {
    if (isRunningUp(alert.strategy_id)) continue;
    const idKey = hodAlertPingIdKey(alert);
    const stKey = hodAlertPingSymTimeKey(alert);
    const replay = memory.keys.has(idKey) || memory.keys.has(stKey);
    memory.keys.add(idKey);
    memory.keys.add(stKey);
    if (replay) continue;
    const ticker = (alert.ticker || '').toUpperCase();
    if (!ticker) continue;
    if (memory.tickers.has(ticker)) continue;
    memory.tickers.add(ticker);
    newRows.push(alert);
  }
  return newRows;
}

/**
 * Admit live arrivals and report whether a desk ping should play.
 * One true per batch is enough -- caller coalesces the oscillator.
 */
export function ingestHodMomoAlertArrivals(arrivals: HodAlertPingArrival[]): boolean {
  const newRows = collectHodMomoNewRows(arrivals);
  const play = soundOn && newRows.length > 0;
  if (play) requestHodMomoAlertPing();
  return play;
}

export function requestHodMomoAlertPing(): void {
  if (!soundOn) return;
  pendingPing = true;
  if (coalesceTimer != null) return;
  coalesceTimer = setTimeout(() => {
    coalesceTimer = null;
    if (!pendingPing || !soundOn) {
      pendingPing = false;
      return;
    }
    pendingPing = false;
    playHodMomoAlertTone();
  }, HOD_MOMO_ALERT_PING_COALESCE_MS);
}

export function playHodMomoAlertTone(): void {
  if (!soundOn) return;
  try {
    if (!audioCtx) audioCtx = new AudioContext();
    const ctx = audioCtx;
    void ctx.resume?.();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = PING_FREQ_HZ;
    gain.gain.value = PING_GAIN;
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + PING_DECAY_SEC);
    osc.stop(ctx.currentTime + PING_STOP_SEC);
  } catch {
    // Web Audio unavailable -- banner toggle still works.
  }
}

async function resumeAudioCtx(): Promise<void> {
  try {
    if (!audioCtx) audioCtx = new AudioContext();
    await audioCtx.resume?.();
  } catch {
    // ignore
  }
}

export function resetHodMomoAlertPingForTests(): void {
  memory.keys.clear();
  memory.tickers.clear();
  audioCtx = null;
  pendingPing = false;
  if (coalesceTimer != null) {
    clearTimeout(coalesceTimer);
    coalesceTimer = null;
  }
  try {
    localStorage.removeItem(HOD_MOMO_ALERT_SOUND_STORAGE_KEY);
  } catch {
    // ignore
  }
  soundOn = HOD_MOMO_ALERT_SOUND_DEFAULT;
}
