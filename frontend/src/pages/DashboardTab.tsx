/**
 * Dashboard tab — short hub pointing users to Settings for config.
 * Exchange filter + Alpaca/scanner live under Settings > General.
 */
export function DashboardTab() {
  return (
    <div className="dashboard-tab dashboard-config" data-testid="dashboard-tab">
      <section className="dashboard-section">
        <h3 className="dashboard-section-title">Configuration</h3>
        <p className="dashboard-section-hint">
          Exchange filter, Alpaca news/listing keys, trade defaults, hotkeys, and
          alerts are in Settings (gear on the top bar).
        </p>
      </section>
    </div>
  );
}
