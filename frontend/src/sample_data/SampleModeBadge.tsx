/**
 * Marking strip for the sample desk (#357) -- one owner, both sample branches.
 *
 * Lives in SampleShell (not the dashboard column) so the sample Trader route is
 * marked too. Reuses the existing .sample-data-banner / .history-banner-btn
 * colours and adds --strip for its own flex contract (sampleModeBadge.css):
 * it sits inside the overflow:hidden .nova-app-stack, so it must take its
 * height off .nova-app-branch rather than add page scroll.
 */
import { SAMPLE_MARKETING_HINT, SAMPLE_MARKETING_LABEL } from './sampleCopy';
import './sampleModeBadge.css';

export function SampleModeBadge({ onExit }: { onExit: () => void }) {
  return (
    <div
      className="sample-data-banner sample-data-banner--strip"
      role="status"
      data-testid="sample-data-badge"
    >
      <span>
        <strong>{SAMPLE_MARKETING_LABEL}</strong>
        {' — '}
        {SAMPLE_MARKETING_HINT}
      </span>
      <button type="button" className="history-banner-btn" onClick={onExit}>
        Exit sample
      </button>
    </div>
  );
}
