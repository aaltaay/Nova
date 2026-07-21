/**
 * Imperative global dialog API — drop-in replacement for window.confirm / alert / prompt.
 * Requires AppDialogHost mounted at the app root (wired in App.tsx).
 */
import {
  APP_DIALOG_ALERT_DEFAULT_TITLE,
  APP_DIALOG_CANCEL_LABEL,
  APP_DIALOG_CONFIRM_DEFAULT_TITLE,
  APP_DIALOG_CONTINUE_LABEL,
  APP_DIALOG_OK_LABEL,
  APP_DIALOG_PROMPT_DEFAULT_TITLE,
} from '../constants';

export type AppDialogTone = 'default' | 'warning' | 'danger';

export interface ConfirmDialogOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: AppDialogTone;
}

export interface AlertDialogOptions {
  title?: string;
  message: string;
  okLabel?: string;
  tone?: AppDialogTone;
}

export interface PromptDialogOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  placeholder?: string;
  /** When set, Confirm stays disabled until the input matches exactly. */
  expectedValue?: string;
  tone?: AppDialogTone;
}

export type AppDialogRequest =
  | ({ kind: 'confirm'; resolve: (ok: boolean) => void } & Required<
      Pick<ConfirmDialogOptions, 'message'>
    > &
      ConfirmDialogOptions)
  | ({ kind: 'alert'; resolve: () => void } & Required<Pick<AlertDialogOptions, 'message'>> &
      AlertDialogOptions)
  | ({ kind: 'prompt'; resolve: (value: string | null) => void } & Required<
      Pick<PromptDialogOptions, 'message'>
    > &
      PromptDialogOptions);

type DialogHandler = (request: AppDialogRequest) => void;

let handler: DialogHandler | null = null;

/** Called by AppDialogHost on mount/unmount. */
export function registerAppDialogHandler(next: DialogHandler | null): void {
  handler = next;
}

function ensureHost(): DialogHandler {
  if (!handler) {
    throw new Error(
      'AppDialogHost is not mounted — wrap the app in <AppDialogHost> before calling confirmApp/alertApp/promptApp',
    );
  }
  return handler;
}

function asMessage(input: string | ConfirmDialogOptions | AlertDialogOptions | PromptDialogOptions): string {
  return typeof input === 'string' ? input : input.message;
}

export function confirmApp(
  input: string | ConfirmDialogOptions,
): Promise<boolean> {
  const opts = typeof input === 'string' ? { message: input } : input;
  return new Promise<boolean>(resolve => {
    ensureHost()({
      kind: 'confirm',
      title: opts.title ?? APP_DIALOG_CONFIRM_DEFAULT_TITLE,
      message: asMessage(opts),
      confirmLabel: opts.confirmLabel ?? APP_DIALOG_CONTINUE_LABEL,
      cancelLabel: opts.cancelLabel ?? APP_DIALOG_CANCEL_LABEL,
      tone: opts.tone ?? 'default',
      resolve,
    });
  });
}

export function alertApp(input: string | AlertDialogOptions): Promise<void> {
  const opts = typeof input === 'string' ? { message: input } : input;
  return new Promise<void>(resolve => {
    ensureHost()({
      kind: 'alert',
      title: opts.title ?? APP_DIALOG_ALERT_DEFAULT_TITLE,
      message: asMessage(opts),
      okLabel: opts.okLabel ?? APP_DIALOG_OK_LABEL,
      tone: opts.tone ?? 'default',
      resolve,
    });
  });
}

export function promptApp(input: string | PromptDialogOptions): Promise<string | null> {
  const opts = typeof input === 'string' ? { message: input } : input;
  return new Promise<string | null>(resolve => {
    ensureHost()({
      kind: 'prompt',
      title: opts.title ?? APP_DIALOG_PROMPT_DEFAULT_TITLE,
      message: asMessage(opts),
      confirmLabel: opts.confirmLabel ?? APP_DIALOG_CONTINUE_LABEL,
      cancelLabel: opts.cancelLabel ?? APP_DIALOG_CANCEL_LABEL,
      placeholder: opts.placeholder,
      expectedValue: opts.expectedValue,
      tone: opts.tone ?? 'default',
      resolve,
    });
  });
}
