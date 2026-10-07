/**
 * The desk side of the agent endpoints (ADR 050), mounted once in the main window's shell (never in a Trader
 * pop-out, the sample desk or the demo): it listens for an agent's show / move and runs it with the desk's
 * own steps, and the notice says what it is doing. Renders nothing until a command comes.
 */
import { useEffect, useRef, useState } from 'react';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { useWorkspace } from '../workspace';
import { AGENT_DESK_NOTICE_DONE_MS } from './agentDeskConstants';
import { listenForAgentCommands } from './agentDeskListen';
import { AgentDeskNotice } from './AgentDeskNotice';
import type { AgentNotice } from './runAgentCommand';
import './agentDesk.css';

const IS_DEMO = import.meta.env.VITE_NOVA_DEMO === '1';

export function AgentDeskHost() {
  const { openStockView } = useWorkspace();
  const openTab = useRef(openStockView);
  openTab.current = openStockView;
  const [notice, setNotice] = useState<AgentNotice | null>(null);

  useEffect(() => {
    if (IS_DEMO || onSampleDesk()) return undefined;
    const controller = new AbortController();
    void listenForAgentCommands(controller.signal, {
      openTab: symbol => openTab.current(symbol),
      notice: setNotice,
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (notice?.state !== 'done' && notice?.state !== 'cancelled') return undefined;
    const shown = notice;
    const timer = window.setTimeout(() => setNotice(current => (current === shown ? null : current)),
      AGENT_DESK_NOTICE_DONE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);

  return notice ? <AgentDeskNotice notice={notice} onClose={() => setNotice(null)} /> : null;
}
