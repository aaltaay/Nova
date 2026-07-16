import type { RefObject } from 'react';

type Props = {
  fileName: string;
  fileRef: RefObject<HTMLInputElement | null>;
  onImportFile: (file: File) => void;
  onExport: () => void;
  onHelp: () => void;
};

export function HotkeyFileToolbar({
  fileName,
  fileRef,
  onImportFile,
  onExport,
  onHelp,
}: Props) {
  return (
    <div className="hotkey-file-row">
      <label>
        HotKey File
        <input type="text" value={fileName} readOnly aria-label="Hotkey file name" />
      </label>
      <input
        ref={fileRef}
        type="file"
        accept=".htk,text/plain"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onImportFile(f);
          e.target.value = '';
        }}
      />
      <button type="button" className="btn-secondary" onClick={() => fileRef.current?.click()}>
        Import…
      </button>
      <button type="button" className="btn-secondary" onClick={onExport}>
        Export
      </button>
      <button type="button" className="btn-secondary" onClick={onHelp}>
        Help
      </button>
    </div>
  );
}
