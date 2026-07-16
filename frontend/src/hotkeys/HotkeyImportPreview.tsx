import type { ImportPreview } from './useHotkeyProfile';

type Props = {
  preview: ImportPreview;
  onConfirm: () => void;
  onCancel: () => void;
};

export function HotkeyImportPreview({ preview, onConfirm, onCancel }: Props) {
  return (
    <div className="hotkey-import-preview" role="dialog" aria-label="Import preview">
      <h4 className="nova-os-section-title">Import preview — {preview.fileName}</h4>
      <p>
        {preview.records.length} record(s)
        {preview.issues.length > 0 && `, ${preview.issues.length} parse issue(s)`}
        . Replace the current profile?
      </p>
      {preview.issues.length > 0 && (
        <ul>
          {preview.issues.slice(0, 8).map((iss) => (
            <li key={`${iss.line}-${iss.message}`}>
              Line {iss.line}: {iss.message}
            </li>
          ))}
        </ul>
      )}
      <div className="form-row">
        <button type="button" onClick={onConfirm}>
          Replace profile
        </button>
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
