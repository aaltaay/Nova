/**
 * Settings > Notifications (mockup v1, 2026-11-18): what your PC sends this phone, on which days and between
 * which hours. Everything is off until you turn it on.
 *
 * The PC keeps these settings and sends every notification, so they hold with Nova closed and the phone
 * locked. Market alerts (HOD Momo, setups, a new leader) come only in your hours; fills and the loss limit
 * come at any time. Nothing here trades, and no rule is worked out on the phone.
 */
import type { ReactNode } from 'react';
import { Bell, BellOff, Minus, Plus } from 'lucide-react';
import { useHotList } from '../../hot_list';
import { BackButton, LinkPill, PhoneScreen } from '../PhoneChrome';
import {
  DAY_LETTERS,
  DAY_NAMES,
  lastSentText,
  stepHours,
  stepWhy,
  toggleDay,
  type HodMomoMode,
  type NotifySettings,
  type ThisPhone,
} from '../notify/phoneNotify';
import { usePhoneNotify } from '../notify/usePhoneNotify';
import './settings.css';
import './notify.css';

const HOD_MODES: readonly { id: HodMomoMode; name: string; said: string }[] = [
  { id: 'off', name: 'Off', said: 'off' },
  { id: 'stars', name: 'Stars', said: 'your stars only' },
  { id: 'all', name: 'All', said: 'every stock' },
];

const PHONE_WORDS: Record<ThisPhone, string> = {
  on: 'On · sent by your PC',
  off: 'Off · this phone gets nothing',
  blocked: 'Blocked for Nova in this phone\'s settings',
  unsupported: 'This browser cannot receive them',
  unknown: 'Reading…',
};

function Switch({ on, label, onChange, why }: { on: boolean; label: string; onChange: (next: boolean) => void; why?: string }) {
  return (
    <>
      <button
        type="button"
        className="ph-set__switch"
        role="switch"
        aria-checked={on}
        aria-label={`${label}: ${on ? 'on' : 'off'}`}
        disabled={Boolean(why)}
        data-why={why}
        onClick={() => onChange(!on)}
      >
        <span><i /></span>
      </button>
      <span className="ph-set__off">{on ? 'On' : 'Off'}</span>
    </>
  );
}

function Row({ name, note, children, testId }: { name: string; note?: string; children: ReactNode; testId?: string }) {
  return (
    <div className="ph-set__row" data-testid={testId}>
      <span className="ph-set__words">
        <b>{name}</b>
        {note ? <i>{note}</i> : null}
      </span>
      {children}
    </div>
  );
}

function Stepper({ which, settings, onStep }: {
  which: 'start' | 'end'; settings: NotifySettings; onStep: (next: { start: string; end: string }) => void;
}) {
  const down = stepHours(settings, which, -1);
  const up = stepHours(settings, which, 1);
  const name = which === 'start' ? 'From' : 'To';
  return (
    <div className="ph-ntf__time">
      <button type="button" aria-label={`${name}: half an hour earlier`} disabled={!down} data-why={down ? undefined : stepWhy(which, -1)} onClick={() => down && onStep(down)}>
        <Minus size={14} aria-hidden="true" />
      </button>
      <b data-testid={`phone-notify-${which}`}>{settings[which]}</b>
      <button type="button" aria-label={`${name}: half an hour later`} disabled={!up} data-why={up ? undefined : stepWhy(which, 1)} onClick={() => up && onStep(up)}>
        <Plus size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

export function NotifyScreen() {
  const n = usePhoneNotify();
  // The hot list's own leaders rule: how many of the Gainers board it takes (the desk's setting).
  const leaders = useHotList().view?.auto?.n ?? null;
  const s = n.view?.settings ?? null;
  const on = n.thisPhone === 'on';
  const phoneWhy = n.thisPhone === 'unsupported'
    ? 'This browser cannot receive notifications. Open Nova in Chrome on the phone, over the https address of your PC.'
    : n.thisPhone === 'blocked'
      ? 'Notifications are blocked for Nova on this phone. Allow them in the phone\'s settings for this site, then come back.'
      : n.thisPhone === 'unknown'
        ? 'Waiting for your PC to answer.'
        : !on && n.view && !n.view.available
          ? n.view.why_unavailable ?? 'Your PC cannot send notifications yet.'
          : undefined;
  const set = (label: string, patch: Partial<NotifySettings>): void => {
    if (s) n.save(label, { ...s, ...patch });
  };

  return (
    <PhoneScreen
      name="notify"
      tab={null}
      header={(
        <div className="ph-head has-back ph-set__head">
          <BackButton to={{ screen: 'settings' }} label="Back to Settings" />
          <div className="ph-head__title">Notifications</div>
          <div className="ph-grow" />
          <LinkPill words="Connected to your PC" />
        </div>
      )}
    >
      <div className="ph-ntf">
        <section>
          <div className="ph-card ph-set__rows">
            <div className="ph-set__row" data-testid="phone-notify-phone">
              <span className="ph-set__icon" data-state={on ? 'open' : 'locked'}>
                {on ? <Bell size={16} aria-hidden="true" /> : <BellOff size={16} aria-hidden="true" />}
              </span>
              <span className="ph-set__words">
                <b>Notify this phone</b>
                <i>{PHONE_WORDS[n.thisPhone]}</i>
              </span>
              <Switch on={on} label="Notify this phone" onChange={n.setThisPhone} why={phoneWhy} />
            </div>
          </div>
        </section>

        {!s ? (
          <div className="ph-empty" role="status" data-testid="phone-notify-absent">{n.error ?? 'Reading your settings from your PC…'}</div>
        ) : (
          <>
            <section>
              <div className="ph-label ph-set__label"><span>Market alerts</span><span className="ph-faint">Only in your hours</span></div>
              <div className="ph-card ph-set__rows">
                <Row name="HOD Momo" note="One per stock every 15 min" testId="phone-notify-hod">
                  <div className="ph-seg ph-ntf__seg" role="group" aria-label="HOD Momo notifications">
                    {HOD_MODES.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        aria-pressed={s.hod_momo === m.id}
                        onClick={() => {
                          if (s.hod_momo !== m.id) set(`HOD Momo notifications: ${m.said}`, { hod_momo: m.id });
                        }}
                      >
                        {m.name}
                      </button>
                    ))}
                  </div>
                </Row>
                <Row name="Setups on your stars" note="Armed · near the trigger · triggered" testId="phone-notify-setups">
                  <Switch on={s.setups} label="Setups on your stars" onChange={(v) => set(`Setups on your stars: ${v ? 'on' : 'off'}`, { setups: v })} />
                </Row>
                <Row name="New leader" note={leaders ? `A stock joins the top ${leaders} Gainers` : 'A stock joins the hot list\'s leaders'} testId="phone-notify-leader">
                  <Switch on={s.new_leader} label="New leader" onChange={(v) => set(`New leader: ${v ? 'on' : 'off'}`, { new_leader: v })} />
                </Row>
              </div>
            </section>

            <section>
              <div className="ph-label ph-set__label"><span>Your hours</span><span className="ph-faint">New York time</span></div>
              <div className="ph-card ph-set__rows">
                <Row name="Days" testId="phone-notify-days">
                  <div className="ph-ntf__days" role="group" aria-label="Days">
                    {DAY_LETTERS.map((letter, day) => (
                      <button
                        // The index is the day itself (0 is Monday): it never reorders.
                        key={DAY_NAMES[day]}
                        type="button"
                        aria-pressed={s.days.includes(day)}
                        aria-label={DAY_NAMES[day]}
                        onClick={() => set(`${DAY_NAMES[day]}: ${s.days.includes(day) ? 'off' : 'on'}`, { days: toggleDay(s.days, day) })}
                      >
                        {letter}
                      </button>
                    ))}
                  </div>
                </Row>
                <div className="ph-set__row" data-testid="phone-notify-hours">
                  <div className="ph-ntf__hours">
                    <i>From</i>
                    <Stepper which="start" settings={s} onStep={(next) => set(`Notify from ${next.start}`, next)} />
                    <i>to</i>
                    <Stepper which="end" settings={s} onStep={(next) => set(`Notify until ${next.end}`, next)} />
                  </div>
                </div>
              </div>
            </section>

            <section>
              <div className="ph-label ph-set__label"><span>Your account</span><span className="ph-faint">Any time</span></div>
              <div className="ph-card ph-set__rows">
                <Row name="Fills" note="Yours, Claude's and the brain's" testId="phone-notify-fills">
                  <Switch on={s.fills} label="Fills" onChange={(v) => set(`Fills: ${v ? 'on' : 'off'}`, { fills: v })} />
                </Row>
                <Row name="Loss limit" note="The warning and the stop" testId="phone-notify-limit">
                  <Switch on={s.loss_limit} label="Loss limit" onChange={(v) => set(`Loss limit: ${v ? 'on' : 'off'}`, { loss_limit: v })} />
                </Row>
              </div>
            </section>

            <div className="ph-ntf__test">
              <span data-testid="phone-notify-last">{lastSentText(n.view?.last_sent ?? null)}</span>
              <button
                type="button"
                className="ph-pill-btn ph-set__btn"
                disabled={!on}
                data-why={on ? undefined : 'Turn on Notify this phone first: a test goes to the phones that are on.'}
                onClick={n.test}
              >
                Send a test
              </button>
            </div>
          </>
        )}
      </div>
    </PhoneScreen>
  );
}
