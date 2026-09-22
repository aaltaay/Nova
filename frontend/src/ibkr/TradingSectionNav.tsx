export type TradingTabSection = 'overview' | 'reports' | 'activity' | 'latency';

const SECTIONS: readonly { id: TradingTabSection; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'reports', label: 'Reports' },
  { id: 'activity', label: 'Activity' },
  { id: 'latency', label: 'Latency' },
];

/** Every section, in nav order -- a host may offer fewer (QA V23). */
export const TRADING_TAB_SECTIONS: readonly TradingTabSection[] = SECTIONS.map(s => s.id);

export function TradingSectionNav({
  section,
  onChange,
  sections = TRADING_TAB_SECTIONS,
}: {
  section: TradingTabSection;
  onChange: (section: TradingTabSection) => void;
  sections?: readonly TradingTabSection[];
}) {
  return (
    <div className="ibkr-section-toggle" role="tablist" aria-label="Account section">
      {SECTIONS.filter(item => sections.includes(item.id)).map(item => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={section === item.id}
          data-testid={`account-section-${item.id}`}
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
