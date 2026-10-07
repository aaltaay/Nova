/** What an agent is doing on this desk right now (ADR 050): one small card, bottom left. */
import { AGENT_DESK_TEXT } from './agentDeskConstants';
import type { AgentNotice } from './runAgentCommand';

export function AgentDeskNotice({ notice, onClose }: { notice: AgentNotice; onClose: () => void }) {
  const label = notice.state === 'done' ? AGENT_DESK_TEXT.done
    : notice.state === 'failed' ? AGENT_DESK_TEXT.failed : AGENT_DESK_TEXT.heading;
  return (
    <div
      className={`nova-agent-notice nova-agent-notice--${notice.state}`}
      role="status"
      aria-live="polite"
      data-testid="agent-desk-notice"
    >
      <div className="nova-agent-notice__head">
        <span className="nova-agent-notice__label">{label}</span>
        <span className="nova-agent-notice__title">{notice.title}</span>
        <button type="button" className="nova-agent-notice__close" onClick={onClose} aria-label={AGENT_DESK_TEXT.close}>
          ×
        </button>
      </div>
      <div className="nova-agent-notice__text">{notice.text}</div>
    </div>
  );
}
