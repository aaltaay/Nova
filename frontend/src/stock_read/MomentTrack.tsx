/**
 * The trade's moment on the 1-minute chart (ADR 037): the badge's track -- Forming, Trigger, Holding,
 * then the exit (Your exit, or Target / stop) -- that moves by itself, and the call in the corner:
 * ENTER NOW, SELL NOW, or what Nova just did, in words. The bell mutes the ping on every Trader tab.
 */
import { useSyncExternalStore } from 'react';
import { tipProps } from '../ux';
import { STEP_NAMES, type Moment, type MomentCall } from './momentModel';
import { isStockReadSoundOn, setStockReadSound, subscribeStockReadSound } from './whoTradesSound';
import './whoTrades.css';

function useSoundOn(): boolean {
  return useSyncExternalStore(subscribeStockReadSound, isStockReadSoundOn, isStockReadSoundOn);
}

const STEP_TIPS: Record<string, string> = {
  Forming: 'The setup is forming, armed or near its trigger.',
  Trigger: 'The trigger printed: the moment to enter.',
  Holding: 'Shares are held.',
  'Your exit': 'The exit is yours: Nova places no sell.',
  'Target / stop': 'Nova holds the exit: the target, the stop.',
};

export function MomentTrack({ moment }: { moment: Moment }) {
  const sound = useSoundOn();
  const steps = [...STEP_NAMES, moment.exitLabel];
  return (
    <div className={`sr-track sr-track--${moment.tone}`} data-testid="moment-track" aria-label="Where the trade stands">
      {steps.map((name, i) => {
        const state = i < moment.step ? 'done' : i === moment.step ? 'now' : 'next';
        return (
          <span
            key={name}
            className={`sr-track__step sr-track__step--${state}`}
            data-state={state}
            {...tipProps(STEP_TIPS[name], name)}
          >
            {state === 'done' ? '✓ ' : ''}
            {name}
          </span>
        );
      })}
      <button
        type="button"
        className="sr-track__bell"
        aria-pressed={sound}
        aria-label={sound ? 'Mute the ping' : 'Hear the ping'}
        onClick={() => setStockReadSound(!sound)}
        {...tipProps(sound ? 'A ping sounds for ENTER NOW, SELL NOW and what Nova just did. Click to mute it on '
          + 'every Trader tab.' : 'The ping is muted on every Trader tab. Click to hear the calls again.', 'Ping')}
        data-testid="moment-bell"
      >
        {sound ? '🔔' : '🔕'}
      </button>
    </div>
  );
}

export function CallBox({ call }: { call: MomentCall }) {
  return (
    <div className={`sr-call sr-call--${call.tone}`} role="status" aria-live="polite" data-testid="moment-call">
      <b className="sr-call__title">{call.title}</b>
      {call.detail && <span className="sr-call__detail">{call.detail}</span>}
    </div>
  );
}
