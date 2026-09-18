/** Reports file import -- CSV or JSON with explicit P/L facts. */
import { useRef, useState } from 'react';
import {
  JOURNAL_IMPORT_ACCEPT,
  JOURNAL_IMPORT_SAMPLE_CSV,
  JOURNAL_IMPORT_SAMPLE_NAME,
} from './importConstants';
import { importJournalFile } from './importJournal';
import type { JournalImportResult } from './types';

interface Props {
  onImported: () => void;
}

function downloadSample(): void {
  const blob = new Blob([JOURNAL_IMPORT_SAMPLE_CSV], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = JOURNAL_IMPORT_SAMPLE_NAME;
  link.click();
  URL.revokeObjectURL(url);
}

function summarize(result: JournalImportResult): string {
  const skipped = result.skipped ?? 0;
  const dupes = result.duplicates ?? 0;
  const extra =
    skipped || dupes
      ? ` Skipped ${skipped}. Duplicates ${dupes}.`
      : '';
  return `Imported ${result.imported} trade${result.imported === 1 ? '' : 's'}.${extra}`;
}

export function ReportsImport({ onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File): Promise<void> {
    setBusy(true);
    setError(null);
    setStatus(`Uploading ${file.name}…`);
    try {
      const result = await importJournalFile(file);
      setStatus(summarize(result));
      if ((result.errors?.length ?? 0) > 0) {
        setError(result.errors!.slice(0, 4).join(' · '));
      }
      if (result.imported > 0) onImported();
    } catch (err) {
      const result = (err as { result?: JournalImportResult }).result;
      setStatus(null);
      const extras = result?.errors?.slice(0, 4).join(' · ');
      setError(
        extras
          ? `${err instanceof Error ? err.message : 'Import failed'} -- ${extras}`
          : err instanceof Error
            ? err.message
            : 'Import failed',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="reports-import" data-testid="reports-import">
      <div className="reports-import-row">
        <p className="reports-import-hint">
          Import closed trades from CSV or JSON. Required: symbol, side (long/short),
          qty, entry_price, exit_price, pnl, closed_at. Nova does not compute P/L or
          commissions. IB Flex is not wired.
        </p>
        <div className="reports-import-actions">
          <button
            type="button"
            className="reports-import-btn"
            onClick={downloadSample}
          >
            Sample CSV
          </button>
          <button
            type="button"
            className="reports-import-btn"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
          >
            {busy ? 'Importing…' : 'Import file'}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={JOURNAL_IMPORT_ACCEPT}
            hidden
            data-testid="reports-import-input"
            onChange={event => {
              const file = event.target.files?.[0];
              event.target.value = '';
              if (file) void handleFile(file);
            }}
          />
        </div>
      </div>
      {status && <p className="reports-status">{status}</p>}
      {error && <p className="reports-status reports-error">{error}</p>}
    </section>
  );
}
