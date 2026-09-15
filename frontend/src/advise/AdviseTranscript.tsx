import { useAdvise } from './AdviseContext';

export function AdviseTranscript() {
  const { run } = useAdvise();
  const events = run?.transcript ?? [];
  if (!events.length) {
    return (
      <div className="advise-transcript advise-transcript--empty" data-testid="advise-transcript">
        Transcript appears here when a debate is running or reopened from the book.
      </div>
    );
  }
  return (
    <ol className="advise-transcript" data-testid="advise-transcript">
      {events.map((event, index) => (
        <li key={`${event.ts ?? 'e'}-${index}`} className="advise-transcript__row">
          <span className="advise-transcript__who">
            {event.agent || event.type}
          </span>
          <span className="advise-transcript__body">
            {event.content || event.message || event.type}
          </span>
        </li>
      ))}
    </ol>
  );
}
