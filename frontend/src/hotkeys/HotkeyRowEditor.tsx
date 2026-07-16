/**
 * Modal editor for a single DAS-style Name / Key / Command row.
 * Saving validates but never activates the command.
 */

import { useEffect, useState } from 'react';
import { formatKeyChord, parseKeyChord } from './htkFormat';
import type { HotkeyKeyChord, HotkeyRecord } from './types';

interface Props {
  record: HotkeyRecord;
  onSave: (patch: Partial<HotkeyRecord>) => void;
  onCancel: () => void;
}

function chordFromKeyboardEvent(e: KeyboardEvent): HotkeyKeyChord | null {
  if (e.key === 'Tab' || e.key === 'Escape') return null;
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return null;
  const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  const parts: string[] = [];
  if (e.ctrlKey) parts.push('Ctrl');
  if (e.shiftKey) parts.push('Shift');
  if (e.altKey) parts.push('Alt');
  if (e.metaKey) parts.push('Win');
  parts.push(key === ' ' ? 'Space' : key);
  return parseKeyChord(parts.join('+'));
}

export function HotkeyRowEditor({ record, onSave, onCancel }: Props) {
  const [name, setName] = useState(record.name);
  const [key, setKey] = useState<HotkeyKeyChord>(record.key);
  const [command, setCommand] = useState(record.command);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    if (!capturing) return;
    const onKeyDown = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === 'Escape') {
        setCapturing(false);
        return;
      }
      const chord = chordFromKeyboardEvent(e);
      if (chord) {
        setKey(chord);
        setCapturing(false);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [capturing]);

  return (
    <div className="hotkey-editor-backdrop" role="dialog" aria-label="Edit hotkey">
      <div className="hotkey-editor">
        <h3 className="nova-os-section-title">Edit Hotkey</h3>
        <p className="na-muted">
          Commands are analyzed only — they will not place orders in this phase.
        </p>
        <label className="hotkey-editor-field">
          <span>Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={99}
          />
        </label>
        <label className="hotkey-editor-field">
          <span>Key</span>
          <div className="hotkey-editor-key-row">
            <input
              value={formatKeyChord(key)}
              onChange={(e) => setKey(parseKeyChord(e.target.value))}
              placeholder="e.g. Shift+1"
            />
            <button
              type="button"
              className={capturing ? 'btn-secondary active' : 'btn-secondary'}
              onClick={() => setCapturing((c) => !c)}
            >
              {capturing ? 'Press keys…' : 'Capture'}
            </button>
          </div>
        </label>
        <label className="hotkey-editor-field">
          <span>Command(s)</span>
          <textarea
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            rows={5}
            spellCheck={false}
            placeholder="ROUTE=LIMIT;Price=Ask+0.10;Share=100;TIF=DAY+;BUY=Send"
          />
        </label>
        <div className="form-row">
          <button
            type="button"
            onClick={() =>
              onSave({
                name: name.trim() || '(unnamed)',
                key,
                command,
              })
            }
          >
            Save
          </button>
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
