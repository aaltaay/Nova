/**
 * The ticket's two small parts: the keypad a share count is typed on, and a value with a minus and a plus.
 * Neither knows anything about an order.
 */
import { useState } from 'react';
import { Delete } from 'lucide-react';

/** A share count typed on a keypad of its own: no system keyboard, so nothing on the screen moves. */
export function SharesSheet({ start, onClose }: { start: number; onClose: (shares: number | null) => void }) {
  const [digits, setDigits] = useState('');
  const shown = digits || String(start);
  const press = (key: string): void => setDigits((d) => (d + key).replace(/^0+/, '').slice(0, 5));
  const value = Number(digits);
  return (
    <div className="ph-sheet" role="dialog" aria-modal="true" aria-label="Shares" data-testid="phone-shares-sheet">
      <div className="ph-pin">
        <div className="ph-pin__title">Shares</div>
        <div className="ph-trade__typed" data-empty={digits ? 'false' : 'true'}>{shown}</div>
        <div className="ph-pin__keys">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((key) => (
            <button key={key} type="button" onClick={() => press(key)}>{key}</button>
          ))}
          <button type="button" className="is-plain" onClick={() => onClose(null)}>Cancel</button>
          <button type="button" onClick={() => press('0')}>0</button>
          <button type="button" className="is-plain" aria-label="Delete the last digit" onClick={() => setDigits((d) => d.slice(0, -1))}>
            <Delete size={20} aria-hidden="true" />
          </button>
        </div>
        <button type="button" className="ph-trade__use" disabled={!(value >= 1)} data-why={value >= 1 ? undefined : 'Type a number of shares first.'} onClick={() => onClose(value)}>
          Use {value >= 1 ? value.toLocaleString('en-US') : '…'} shares
        </button>
      </div>
    </div>
  );
}

export function Stepper({ label, text, muted, onDown, onUp, name, why }: {
  label: string;
  text: string;
  muted?: boolean;
  onDown?: () => void;
  onUp?: () => void;
  name: string;
  /** Why a step that cannot be taken cannot. */
  why: string;
}) {
  return (
    <div className="ph-step" data-muted={muted ? 'true' : 'false'}>
      <i>{label}</i>
      <b>{text}</b>
      <button type="button" aria-label={`${name} down`} disabled={!onDown} data-why={onDown ? undefined : why} onClick={onDown}>−</button>
      <button type="button" aria-label={`${name} up`} disabled={!onUp} data-why={onUp ? undefined : why} onClick={onUp}>+</button>
    </div>
  );
}
