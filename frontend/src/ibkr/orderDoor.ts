/**
 * Which door of the backend this page's orders go through.
 *
 * The desk's is `/api/ibkr` (the API key opens it; `novaFetch` adds the key). The phone's is `/api/phone`
 * (ADR 070): another device may write nowhere else, and its PIN's session opens it. The routes under both
 * are the same shape (`POST /order`, `DELETE /orders?symbol=`, `DELETE /orders?all_symbols=true`), and the
 * phone's hands each order to the desk's own handler, so the ticket code that builds and sends an order
 * is one piece of code for both. The phone's page installs its door once, when it mounts.
 */
export interface OrderDoor {
  /** The path prefix under the API base: `/api/ibkr` or `/api/phone`. */
  prefix: string;
  /** Headers every write through this door carries (the phone's session), read at send time. */
  headers: () => Record<string, string>;
}

const DESK_DOOR: OrderDoor = { prefix: '/api/ibkr', headers: () => ({}) };

let door: OrderDoor = DESK_DOOR;

/** Install another door (the phone's); `null` puts the desk's back. */
export function setOrderDoor(next: OrderDoor | null): void {
  door = next ?? DESK_DOOR;
}

export function orderDoor(): OrderDoor {
  return door;
}
