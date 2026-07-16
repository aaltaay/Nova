type Summary = {
  translatable_later: number;
  backend_required: number;
  das_ibkr_specific: number;
  invalid_unsafe: number;
  conflicts: number;
};

export function HotkeySummaryBar({ summary }: { summary: Summary }) {
  return (
    <div className="hotkey-summary">
      <span>Translatable: {summary.translatable_later}</span>
      <span>Backend: {summary.backend_required}</span>
      <span>DAS-specific: {summary.das_ibkr_specific}</span>
      <span>Invalid: {summary.invalid_unsafe}</span>
      <span>Conflicts: {summary.conflicts}</span>
    </div>
  );
}
