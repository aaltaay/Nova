export type TradingTabSection = 'overview' | 'reports' | 'latency';

const SECTIONS: readonly { id: TradingTabSection; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'reports', label: 'Reports' },
  { id: 'latency', label: 'Latency' },
];

export function TradingSectionNav({
  section,
  onChange,
}: {
  section: TradingTabSection;
  onChange: (section: TradingTabSection) => void;
}) {
  return (
    <div className="ibkr-section-toggle" role="tablist" aria-label="Account section">
      {SECTIONS.map(item => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={section === item.id}
          className={
            section === item.id
              ? 'ibkr-section-toggle-btn active'
              : 'ibkr-section-toggle-btn'
          }
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
