/** Today's hot list on the desk (ADR 043). */
export const HOT_LIST_PATH = '/api/hot-list';
/** One read for every window part that shows the list (the Trader's star, the Bots page). */
export const HOT_LIST_POLL_MS = 10_000;
export const HOT_LIST_AUTO_CHOICES = [3, 5, 10, 0] as const;
