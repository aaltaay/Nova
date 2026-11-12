/**
 * The phone PIN, asked on a keypad of its own (no system keyboard, so nothing on the screen moves).
 * The six digits live in this component only until the door answers, and are never stored.
 */
import { useCallback, useState } from 'react';
import { Delete, Smartphone } from 'lucide-react';
import type { PhoneDoor } from '../phone_link';

const PIN_LENGTH = 6;
const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9'] as const;
export const PIN_NOT_SET = 'No phone PIN yet. Set one on your PC: py -3 tools/set_phone_pin.py';

export function PhonePinSheet({ door, pinSet, onClose }: {
  door: PhoneDoor;
  pinSet: boolean | null;
  onClose: (unlocked: boolean) => void;
}) {
  const [digits, setDigits] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback((pin: string) => {
    setBusy(true);
    void door.unlock(pin).then((answer) => {
      setBusy(false);
      setDigits('');
      if (answer.ok) onClose(true);
      else setError(answer.text);
    });
  }, [door, onClose]);

  const press = (key: string): void => {
    if (busy || digits.length >= PIN_LENGTH) return;
    const next = digits + key;
    setError(null);
    setDigits(next);
    if (next.length === PIN_LENGTH) submit(next);
  };

  const words = error ?? (pinSet === false ? PIN_NOT_SET : busy ? 'Checking…' : 'Unlocks this phone for 8 hours.');
  return (
    <div className="ph-sheet" role="dialog" aria-modal="true" aria-label="Enter your phone PIN" data-testid="phone-pin-sheet">
      <div className="ph-pin">
        <div className="ph-pin__icon" aria-hidden="true"><Smartphone size={20} /></div>
        <div className="ph-pin__title">Phone PIN</div>
        <div className="ph-pin__dots" aria-label={`${digits.length} of ${PIN_LENGTH} digits entered`}>
          {Array.from({ length: PIN_LENGTH }, (_, i) => (
            <i key={i} className={i < digits.length ? 'is-on' : ''} />
          ))}
        </div>
        <div className={`ph-pin__words${error || pinSet === false ? ' is-bad' : ''}`} role="status">{words}</div>
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
