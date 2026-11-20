/**
 * A PIN asked on a keypad of its own (no system keyboard, so nothing on the screen moves). Two uses:
 *
 * - `unlock`: the PIN that unlocks the phone -- the one the operator types on the PC, unless the phone was given
 *   one of its own.
 * - `live`: the Live PIN that opens the desk's padlock on Live (ADR 070 amendment 2026-11-20). It goes to the PC
 *   with the request that opens the padlock, and the PC judges it with its own rule: the PC's PIN, counted with the
 *   wrong ones typed there.
 *
 * The six digits live in this component only until the door answers, and are never stored.
 */
import { useCallback, useState } from 'react';
import { Delete, LockOpen, Smartphone } from 'lucide-react';
import type { Answer, PhoneDoor, PhoneStatus } from '../phone_link';

const PIN_LENGTH = 6;
const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9'] as const;
export const PIN_NOT_SET = 'No PIN is set on your PC yet. Set it there: py -3 tools/set_live_arm_pin.py';
/** What the Live PIN sheet says before a digit is typed. */
export const LIVE_PIN_WORDS = 'Opens the padlock on Live: real money, sent to IBKR. The Live PIN you type on your PC.';

export type PinUse = 'unlock' | 'live';

const SHEET: Record<PinUse, { title: string; label: string; words: string; send: (door: PhoneDoor, pin: string) => Promise<Answer> }> = {
  unlock: {
    title: 'Your PIN',
    label: 'Enter your PIN',
    words: 'The same PIN as on your PC. Unlocks this phone for 8 hours.',
    send: (door, pin) => door.unlock(pin),
  },
  live: {
    title: 'Live PIN',
    label: 'Enter your Live PIN to open the padlock on Live',
    words: LIVE_PIN_WORDS,
    send: (door, pin) => door.arm(true, pin),
  },
};

export function PhonePinSheet({ door, pinSet, onClose, use = 'unlock' }: {
  door: PhoneDoor;
  pinSet: boolean | null;
  /** `done`: the desk did what the PIN was for; `status` is its answer then (the venue it did it on). */
  onClose: (done: boolean, status?: PhoneStatus) => void;
  use?: PinUse;
}) {
  const [digits, setDigits] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sheet = SHEET[use];

  const submit = useCallback((pin: string) => {
    setBusy(true);
    void sheet.send(door, pin).then((answer) => {
      setBusy(false);
      setDigits('');
      if (answer.ok) onClose(true, answer.status);
      else setError(answer.text);
    });
  }, [door, onClose, sheet]);

  const press = (key: string): void => {
    if (busy || digits.length >= PIN_LENGTH) return;
    const next = digits + key;
    setError(null);
    setDigits(next);
    if (next.length === PIN_LENGTH) submit(next);
  };

  // The phone's own unlock knows whether a PIN exists; the Live padlock's answer says so in the PC's words.
  const notSet = use === 'unlock' && pinSet === false;
  const words = error ?? (notSet ? PIN_NOT_SET : busy ? 'Checking…' : sheet.words);
  return (
    <div className="ph-sheet" role="dialog" aria-modal="true" aria-label={sheet.label} data-testid="phone-pin-sheet" data-use={use}>
      <div className="ph-pin">
        <div className="ph-pin__icon" aria-hidden="true">{use === 'live' ? <LockOpen size={20} /> : <Smartphone size={20} />}</div>
        <div className="ph-pin__title">{sheet.title}</div>
        <div className="ph-pin__dots" aria-label={`${digits.length} of ${PIN_LENGTH} digits entered`}>
          {Array.from({ length: PIN_LENGTH }, (_, i) => (
            <i key={i} className={i < digits.length ? 'is-on' : ''} />
          ))}
        </div>
        <div className={`ph-pin__words${error || notSet ? ' is-bad' : ''}`} role="status">{words}</div>
        <div className="ph-pin__keys">
          {KEYS.map((key) => (
            <button key={key} type="button" onClick={() => press(key)}>{key}</button>
          ))}
          <button type="button" className="is-plain" onClick={() => onClose(false)}>Cancel</button>
          <button type="button" onClick={() => press('0')}>0</button>
          <button
            type="button"
            className="is-plain"
            aria-label="Delete the last digit"
            onClick={() => { if (!busy) setDigits((d) => d.slice(0, -1)); }}
          >
            <Delete size={20} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
