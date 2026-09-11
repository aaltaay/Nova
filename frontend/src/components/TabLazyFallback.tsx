/** Suspense placeholder for route/tab code-split chunks (D-031). */
import { TAB_CHUNK_LOADING } from '../constants';

export function TabLazyFallback() {
  return (
    <div className="empty-state" role="status">
      {TAB_CHUNK_LOADING}
    </div>
  );
}
