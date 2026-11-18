/**
 * The notification settings on every phone screen that shows them: the Notifications screen, the row in
 * Settings that leads to it, and the line over Scan's HOD Momo list. One read, shared; every change is a
 * write through the phone's door, answered by the banner, and the screen then shows what the PC kept.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import type { PhoneDoor } from '../../phone_link';
import { usePhoneSession } from '../PhoneSession';
import { parseNotifyView, type NotifySettings, type NotifyView, type ThisPhone } from './phoneNotify';
import { currentAddress, deviceId, pushPermission, subscribePush, unsubscribePush } from './pushClient';

interface NotifyState {
  view: NotifyView | null;
  /** Why the settings could not be read; null while they were, or before the first read. */
  error: string | null;
  /** This phone's id on the PC's list, when it has a push address. */
  deviceId: string | null;
  /** The phone's own answer was read. */
  phoneRead: boolean;
}

const OLD_BACKEND = 'Nova on your PC is older than this page: restart it to update, then notifications can be set.';
const NO_ANSWER = 'Nova on your PC did not answer.';

let state: NotifyState = { view: null, error: null, deviceId: null, phoneRead: false };
let reading: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: Partial<NotifyState>): void {
  state = { ...state, ...next };
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

async function readPhone(): Promise<void> {
  try {
    const address = await currentAddress();
    publish({ deviceId: address ? await deviceId(address.endpoint) : null, phoneRead: true });
  } catch (err) {
    console.warn('[Nova phone] could not read this phone\'s push address', err);
    publish({ deviceId: null, phoneRead: true });
  }
}

function readAll(door: PhoneDoor): Promise<void> {
  if (reading) return reading;
  reading = (async () => {
    try {
      const [res] = await Promise.all([door.notifyRead(), readPhone()]);
      if (res.http === 200) {
        const view = parseNotifyView(res.body);
        publish(view ? { view, error: null } : { error: 'Nova sent notification settings this page cannot read. Reload the page.' });
      } else {
        publish({ error: res.http === 404 ? OLD_BACKEND : NO_ANSWER });
      }
    } finally {
      reading = null;
    }
  })();
  return reading;
}

function thisPhoneOf(s: NotifyState): ThisPhone {
  const permission = pushPermission();
  if (permission === 'unsupported') return 'unsupported';
  if (permission === 'denied') return 'blocked';
  if (!s.view || !s.phoneRead) return 'unknown';
  return s.deviceId != null && s.view.device_ids.includes(s.deviceId) ? 'on' : 'off';
}

export interface PhoneNotify {
  view: NotifyView | null;
  error: string | null;
  thisPhone: ThisPhone;
  /** Change the settings: the PC keeps the whole of what it is sent. */
  save: (label: string, next: NotifySettings) => void;
  /** This phone's switch: ask Android, subscribe, tell the PC; or drop the address on both. */
  setThisPhone: (on: boolean) => void;
  /** Have the PC send one notification now. */
  test: () => void;
}

export function usePhoneNotify(): PhoneNotify {
  const { door, send, notify, askPin } = usePhoneSession();
  const snapshot = useSyncExternalStore(subscribe, () => state, () => state);
  useEffect(() => {
    void readAll(door);
  }, [door]);

  const took = useCallback((view: unknown): void => {
    const parsed = parseNotifyView(view);
    if (parsed) publish({ view: parsed, error: null });
    void readAll(door);
  }, [door]);

  const save = useCallback((label: string, next: NotifySettings) => {
    send(label, async (d) => {
      const answer = await d.notifyWrite('settings', next, () => `${label}.`);
      if (answer.ok) took(answer.view);
      return answer;
    });
  }, [send, took]);

  const setThisPhone = useCallback((on: boolean) => {
    if (!on) {
      send('Stop notifying this phone', async (d) => {
        const address = await unsubscribePush();
        if (!address) {
          await readPhone();
          return { ok: true, ms: 0, text: 'This phone was not subscribed.' };
        }
        const answer = await d.notifyWrite('unsubscribe', { endpoint: address.endpoint }, () => 'This phone gets no notifications now.');
        await readPhone();
        if (answer.ok) took(answer.view);
        return answer;
      });
      return;
    }
    if (!state.view?.available) {
      notify({ tone: 'refused', title: 'NOT DONE · Notify this phone', note: state.view?.why_unavailable ?? state.error ?? NO_ANSWER });
      return;
    }
    // Android only asks for permission inside the tap itself, so the PIN (which ends the tap) comes first.
    if (!door.hasSession()) {
      askPin(() => notify({ tone: 'done', title: 'Unlocked · tap the switch again', note: 'The phone asks for permission on that tap.' }));
      return;
    }
    notify({ tone: 'sending', title: 'Sending · Notify this phone', note: 'Asking the phone, then your PC.' });
    void (async () => {
      // The PC makes its sending key the first time a phone asks; the phone subscribes to its public half.
      let key = state.view?.public_key ?? null;
      if (!key) {
        const made = await door.notifyWrite('key', {}, () => 'Your PC made its sending key.');
        key = parseNotifyView(made.view)?.public_key ?? null;
        if (!made.ok || !key) return { ok: false as const, why: made.ok ? 'Your PC gave no sending key.' : made.text };
      }
      return subscribePush(key);
    })().then(async (result) => {
      if (!result.ok) {
        notify({ tone: 'refused', title: 'NOT DONE · Notify this phone', note: result.why });
        return;
      }
      const answer = await door.notifyWrite('subscribe', result.address, () => 'This phone is subscribed.');
      await readPhone();
      if (answer.ok) {
        took(answer.view);
        notify({ tone: 'done', title: 'This phone gets notifications', note: 'Choose what to send below. Send a test to see one.' });
      } else {
        notify({ tone: 'refused', title: 'NOT DONE · Notify this phone', note: answer.text });
      }
    });
  }, [askPin, door, notify, send, took]);

  const test = useCallback(() => {
    send('Send a test', async (d) => {
      const answer = await d.notifyWrite('test', {}, (b) => (typeof b.text === 'string' ? b.text : 'Sent. It should arrive in a few seconds.'));
      void readAll(door);
      return answer;
    });
  }, [door, send]);

  return { view: snapshot.view, error: snapshot.error, thisPhone: thisPhoneOf(snapshot), save, setThisPhone, test };
}

export function resetPhoneNotifyForTests(): void {
  state = { view: null, error: null, deviceId: null, phoneRead: false };
  reading = null;
  listeners.clear();
}
