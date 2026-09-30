/**
 * The Session Record's desk side (the capture feature's barrel): what other
 * features may use of it -- the record / stop door, the recording set, and the
 * hold-to-stop button -- without reaching into its files.
 */
export {
  getRecordingSymbols,
  getSessionRecordError,
  getSessionRecordVersion,
  isTabRecording,
  startTabRecord,
  stopTabRecord,
  subscribeSessionRecord,
  useRecordingSymbols,
} from './sessionRecordStore';
export { HoldToStopButton } from './HoldToStopButton';
export { CAPTURE_STOP_HOLD_HINT, captureStopHoldLabel } from './constants';
