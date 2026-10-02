/** Public close-of-day reminder API -- cross-feature imports use this barrel (ADR 005). */
export { CloseReminders, type CloseRemindersProps } from './CloseReminders';
export {
  dismissCloseReminder,
  dueCloseReminders,
  etClock,
  getCloseReminders,
  noteCloseReminders,
  stageAt,
  subscribeCloseReminders,
  type CloseReminder,
  type CloseReminderStage,
  type HeldPosition,
} from './closeReminderStore';
