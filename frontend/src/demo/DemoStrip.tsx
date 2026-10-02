/**
 * The strip under the header on the public demo (ADR 043): says what the page is on every view,
 * and points at the repository. Only the demo build mounts it (appLazy.LazyDemoStrip).
 */
import { DEMO_REPO_URL } from './demoFlag';
import './demoStrip.css';

const SITE_URL = 'https://nova.altaystudio.com/';

export default function DemoStrip() {
  return (
    <div className="sample-data-banner demo-strip" role="status" data-testid="demo-strip">
      <span className="demo-strip__text">
        <span className="demo-strip__chip">Live demo</span>
        <strong>Nova Marketing Sample Data</strong>
        {' — '}
        a sample morning, running in your browser. No live market, no real account, and nothing you click is sent anywhere.
      </span>
      <span className="demo-strip__links">
        <a className="history-banner-btn" href={SITE_URL}>About Nova</a>
        <a className="history-banner-btn demo-strip__cta" href={DEMO_REPO_URL} target="_blank" rel="noopener noreferrer">
          Get Nova on GitHub
        </a>
      </span>
    </div>
  );
}
