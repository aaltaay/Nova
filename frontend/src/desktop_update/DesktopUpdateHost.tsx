/**
 * The desktop app's update notice and What's new card, mounted once in the main
 * window's shell (not in Trader pop-outs). Renders nothing in a browser or
 * until the Electron main process has something to say.
 */
import { UpdateNotice } from './UpdateNotice';
import { useDesktopUpdate, type DesktopUpdatesBridge } from './useDesktopUpdate';
import { WhatsNewCard } from './WhatsNewCard';
import './desktopUpdate.css';

export function DesktopUpdateHost({ bridge }: { bridge?: DesktopUpdatesBridge | null } = {}) {
  const { view, act } = useDesktopUpdate(bridge);
  if (!view) return null;
  return (
    <>
      {view.notice && <UpdateNotice notice={view.notice} act={act} />}
      {view.whatsNew && <WhatsNewCard whatsNew={view.whatsNew} act={act} />}
    </>
  );
}
