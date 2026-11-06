/**
 * Point the desk's venue pill at Sim after the API already moved the view.
 * This does not post `/api/desk/venue`, so it does not cancel working orders.
 */
import { confirmDeskVenue } from '../ibkr';

export function viewToSim(): void {
  confirmDeskVenue('sim');
}
