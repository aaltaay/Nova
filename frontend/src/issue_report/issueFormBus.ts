/**
 * One door to the issue form: the What's new card's "File an issue" button and Help > File an
 * Issue… (through the update view) call `openIssueForm`; the host mounted in the main window
 * listens. A request with no host listening does nothing.
 */
type Listener = () => void;

const listeners = new Set<Listener>();

export function openIssueForm(): void {
  for (const listener of listeners) listener();
}

export function onIssueFormOpen(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
