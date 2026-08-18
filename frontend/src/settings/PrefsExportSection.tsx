import { useRef, useState } from 'react';
import {
  downloadPrefsBundle,
  importPrefsBundle,
  readPrefsBundleFile,
} from './prefsBundle';

export function PrefsExportSection() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<string | null>(null);

  return (
    <section className="settings-block" data-testid="prefs-export">
      <h3 className="settings-block-title">Desk preferences</h3>
      <p className="settings-block-hint">
        Download or restore layout, hotkeys, theme, and trade defaults stored in this
        browser. Session-only trader tabs are not included.
      </p>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button
          type="button"
          className="ibkr-btn-secondary"
          onClick={() => {
            downloadPrefsBundle();
            setStatus('Downloaded nova-prefs.json');
          }}
        >
          Export prefs
        </button>
        <button
          type="button"
          className="ibkr-btn-secondary"
          onClick={() => inputRef.current?.click()}
        >
          Import prefs
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={event => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (!file) return;
            void readPrefsBundleFile(file)
              .then(bundle => {
                const n = importPrefsBundle(bundle);
                setStatus(`Imported ${n} keys -- reload to apply layout`);
              })
              .catch(err => {
                setStatus(err instanceof Error ? err.message : 'Import failed');
              });
          }}
        />
      </div>
      {status && <p className="settings-block-hint">{status}</p>}
    </section>
  );
}
