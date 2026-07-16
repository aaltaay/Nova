import {
  HOTKEY_EVIDENCE_LABELS,
  type HotkeyRecord,
  type HotkeyRecordAnalysis,
} from './types';

type Props = {
  selected: HotkeyRecord;
  analysis: HotkeyRecordAnalysis;
};

export function HotkeySelectedDetail({ selected, analysis }: Props) {
  return (
    <div className="hotkey-detail">
      <h4 className="nova-os-section-title">Selected: {selected.name}</h4>
      <p className="na-muted">
        Evidence: {HOTKEY_EVIDENCE_LABELS[analysis.evidence]}
      </p>
      {analysis.diagnostics.length > 0 ? (
        <ul>
          {analysis.diagnostics.map((d) => (
            <li key={`${d.code}-${d.message}`}>{d.message}</li>
          ))}
        </ul>
      ) : (
        <p className="na-muted">No diagnostics.</p>
      )}
    </div>
  );
}
