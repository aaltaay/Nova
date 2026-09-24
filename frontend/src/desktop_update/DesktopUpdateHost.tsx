/**
 * The desktop app's update notice and What's new card, mounted once in the main
 * window's shell (not in Trader pop-outs). Renders nothing in a browser or
 * until the Electron main process has something to say. Also carries Help > File
 * an Issue… to the issue form: a request made after this page subscribed opens it
 * (the one the first view carries is older than the page, so it is not replayed).
 */
import { useEffect, useRef } from 'react';
import { openIssueForm } from '../issue_report';
import { UpdateNotice } from './UpdateNotice';
import { useDesktopUpdate, type DesktopUpdatesBridge } from './useDesktopUpdate';
import { WhatsNewCard } from './WhatsNewCard';
import './desktopUpdate.css';

export function DesktopUpdateHost({ bridge }: { bridge?: DesktopUpdatesBridge | null } = {}) {
  const { view, act } = useDesktopUpdate(bridge);
  const requested = view ? view.fileIssueRequestedAt : undefined;
  const seen = useRef<number | null | undefined>(undefined);
  useEffect(() => {
    if (requested === undefined) return;
    if (seen.current !== undefined && requested !== null && requested !== seen.current) openIssueForm();
    seen.current = requested;
  }, [requested]);
  if (!view) return null;
  return (
    <>
      {view.notice && <UpdateNotice notice={view.notice} act={act} />}
      {view.whatsNew && <WhatsNewCard whatsNew={view.whatsNew} act={act} />}
    </>
  );
}
