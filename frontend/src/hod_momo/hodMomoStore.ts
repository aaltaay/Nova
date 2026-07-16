/**
 * Module-level external store for HOD Momo alerts.
 * Single WebSocket instance shared across the entire app lifetime.
 * Components subscribe via useSyncExternalStore so only the subscribing
 * component re-renders when the store changes — not the full DashboardPage.
 *
 * Two subscriber tiers:
 *   - alerts tier: full { alerts, totalToday, connected, strategyCounts }
 *     — subscribed only by HodMomoTab when the tab is active.
 *   - badge tier: { totalToday, connected }, throttled to HOD_MOMO_BADGE_THROTTLE_MS
 *     — subscribed by DashboardPage for the tab badge at all times.
 */
import { useSyncExternalStore } from 'react';
import {
  HOD_MOMO_ALERT_BATCH_MS,
  HOD_MOMO_BADGE_THROTTLE_MS,
  WS_BASE_URL,
} from '../constants';
import type { AlertObject } from './types';

// ── Store state ───────────────────────────────────────────────────────────────

export interface HodMomoAlertsSnapshot {
  alerts: AlertObject[];
  totalToday: number;
  connected: boolean;
  strategyCounts: Record<number, number>;
}

export interface HodMomoBadgeSnapshot {
  totalToday: number;
  connected: boolean;
}

// Module-level mutable state (intentionally not reactive itself)
let _alerts: AlertObject[] = [];
let _totalToday = 0;
let _connected = false;
let _strategyCounts: Record<number, number> = {};

// Stable snapshot objects — replaced atomically on each notify so
// useSyncExternalStore's reference-equality check triggers re-renders correctly.
let _alertsSnap: HodMomoAlertsSnapshot = { alerts: [], totalToday: 0, connected: false, strategyCounts: {} };
let _badgeSnap: HodMomoBadgeSnapshot = { totalToday: 0, connected: false };

const _alertsSubs = new Set<() => void>();
const _badgeSubs = new Set<() => void>();

// ── WS lifecycle ──────────────────────────────────────────────────────────────

let _ws: WebSocket | null = null;
let _backoff = 1000;
let _seenIds = new Set<string>();
let _pending: AlertObject[] = [];
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
let _badgeThrottle: ReturnType<typeof setTimeout> | null = null;
let _started = false;
let _stopped = false;

function _notifyAlerts() {
  _alertsSnap = { alerts: _alerts, totalToday: _totalToday, connected: _connected, strategyCounts: _strategyCounts };
  for (const fn of _alertsSubs) fn();
}

function _notifyBadgeThrottled() {
  if (_badgeThrottle != null) return;
  _badgeThrottle = setTimeout(() => {
    _badgeThrottle = null;
    _badgeSnap = { totalToday: _totalToday, connected: _connected };
    for (const fn of _badgeSubs) fn();
  }, HOD_MOMO_BADGE_THROTTLE_MS);
}

function _flushPending() {
  _flushTimer = null;
  if (_pending.length === 0) return;
  const batch = _pending;
  _pending = [];
  const nextCounts = { ..._strategyCounts };
  for (const alert of batch) {
    nextCounts[alert.strategy_id] = (nextCounts[alert.strategy_id] ?? 0) + 1;
  }
  _alerts = [...batch, ..._alerts];
  _totalToday = _alerts.length;
  _strategyCounts = nextCounts;
  _notifyAlerts();
  _notifyBadgeThrottled();
}

function _scheduleFlush() {
  if (_flushTimer != null) return;
  _flushTimer = setTimeout(_flushPending, HOD_MOMO_ALERT_BATCH_MS);
}

function _connect() {
  if (_stopped) return;
  const ws = new WebSocket(`${WS_BASE_URL}/ws/hod-momo`);
  _ws = ws;

  ws.onopen = () => {
    if (_ws !== ws) return;
    _connected = true;
    _backoff = 1000;
    _badgeSnap = { totalToday: _totalToday, connected: true };
    for (const fn of _badgeSubs) fn();
  };

  ws.onmessage = (e) => {
    if (_ws !== ws) return;
    try {
      const msg = JSON.parse(e.data as string);
      if (msg.type === 'initial') {
        _pending = [];
        if (_flushTimer != null) { clearTimeout(_flushTimer); _flushTimer = null; }
        const list = Array.isArray(msg.alerts) ? (msg.alerts as AlertObject[]) : [];
        _seenIds = new Set(list.map(a => a.id));
        const counts: Record<number, number> = {};
        for (const a of list) {
          counts[a.strategy_id] = (counts[a.strategy_id] ?? 0) + 1;
        }
        _alerts = list;
        _totalToday = typeof msg.total === 'number' && msg.total >= 0 ? msg.total : list.length;
        _strategyCounts = counts;
        _notifyAlerts();
        _notifyBadgeThrottled();
      } else if (msg.type === 'alert' && msg.alert) {
        const alert = msg.alert as AlertObject;
        if (_seenIds.has(alert.id)) return;
        _seenIds.add(alert.id);
        _pending.push(alert);
        _scheduleFlush();
      }
    } catch {
      // ignore parse errors
    }
  };

  ws.onerror = () => {
    if (_ws !== ws) return;
    _connected = false;
  };

  ws.onclose = () => {
    if (_ws !== ws) return;
    _connected = false;
    if (_stopped) return;
    const delay = _backoff;
    _backoff = Math.min(delay * 2, 30_000);
    setTimeout(_connect, delay);
  };
}

/** Start the store's WebSocket connection. Idempotent — safe to call multiple times. */
export function startHodMomoStore() {
  if (_started) return;
  _started = true;
  _stopped = false;
  _connect();
}

/** Stop the store and close the WebSocket. Resets started flag so startHodMomoStore can be called again. */
export function stopHodMomoStore() {
  _stopped = true;
  _started = false;
  if (_flushTimer != null) { clearTimeout(_flushTimer); _flushTimer = null; }
  if (_badgeThrottle != null) { clearTimeout(_badgeThrottle); _badgeThrottle = null; }
  const ws = _ws;
  if (ws) {
    ws.onopen = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    ws.close();
  }
  _ws = null;
}

// ── useSyncExternalStore bindings ─────────────────────────────────────────────

function _subscribeAlerts(fn: () => void): () => void {
  _alertsSubs.add(fn);
  return () => { _alertsSubs.delete(fn); };
}

function _getAlertsSnap(): HodMomoAlertsSnapshot { return _alertsSnap; }

function _subscribeBadge(fn: () => void): () => void {
  _badgeSubs.add(fn);
  return () => { _badgeSubs.delete(fn); };
}

function _getBadgeSnap(): HodMomoBadgeSnapshot { return _badgeSnap; }

/** Full alert list + counts. Subscribe only when the HOD tab is active. */
export function useHodMomoAlerts(): HodMomoAlertsSnapshot {
  return useSyncExternalStore(_subscribeAlerts, _getAlertsSnap, _getAlertsSnap);
}

/** Throttled badge data for the tab header. Low-cost — safe to subscribe always. */
export function useHodMomoBadge(): HodMomoBadgeSnapshot {
  return useSyncExternalStore(_subscribeBadge, _getBadgeSnap, _getBadgeSnap);
}
