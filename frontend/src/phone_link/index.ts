/** The phone link's public surface for other folders (ADR 005): where the API is, the door, the link's arithmetic. */
export {
  PhoneDoor,
  closingOrder,
  orderStamp,
  refusalText,
  venueMovedText,
  type Answer,
  type OrderContext,
  type PhoneStatus,
  type SimClockMove,
  type VenueEffects,
} from './linkOrders';
export {
  CLOCK_SAMPLES_KEEP,
  LINK_LIMIT_MS,
  Outages,
  Rolling,
  apiBaseFor,
  bestClock,
  clockSample,
  durationText,
  wsBaseFor,
  type ClockSample,
  type Spread,
} from './linkStats';
