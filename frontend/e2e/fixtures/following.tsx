import { createRoot } from 'react-dom/client';
import { FollowedTradersPage } from '../../src/followed_traders';
import { installHoverTip } from '../../src/ux/hoverTip';
import { installWhyTip } from '../../src/ux/whyTip';
import '../../src/index.css';

// The Following page in the desk's slot (App.tsx: .nova-scanner-desk-slot, a column that never scrolls), sized like
// the window's content area beside the nav rail. API replies are mocked by the spec.
function Desk() {
  return (
    <div style={{ height: '100vh', display: 'flex', background: 'var(--nova-bg, #000)' }}>
      <div className="nova-scanner-desk-slot">
        <FollowedTradersPage />
      </div>
    </div>
  );
}

installHoverTip();
installWhyTip();
createRoot(document.getElementById('root')!).render(<Desk />);
