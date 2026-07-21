/**
 * Root host for confirmApp / alertApp / promptApp — styled AlertDialog UI.
 * Mount once near the app root so imperative callers (hooks, pure helpers) work.
 */
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  registerAppDialogHandler,
  type AppDialogRequest,
  type AppDialogTone,
} from './appDialogApi';
import './appDialog.css';

interface Props {
  children: ReactNode;
}

function actionClass(tone: AppDialogTone | undefined): string | undefined {
  if (tone === 'danger') return 'app-dialog-action--danger';
  if (tone === 'warning') return 'app-dialog-action--warning';
  return undefined;
}

export function AppDialogHost({ children }: Props) {
  const [queue, setQueue] = useState<AppDialogRequest[]>([]);
  const active = queue[0] ?? null;
  const inputId = useId();
  const [promptValue, setPromptValue] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    registerAppDialogHandler(request => {
      setQueue(prev => [...prev, request]);
    });
    return () => registerAppDialogHandler(null);
  }, []);

  useEffect(() => {
    if (active?.kind === 'prompt') {
      setPromptValue('');
      const t = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [active]);

  function dismissConfirm(ok: boolean) {
    if (!active || active.kind !== 'confirm') return;
    active.resolve(ok);
    setQueue(prev => prev.slice(1));
  }

  function dismissAlert() {
    if (!active || active.kind !== 'alert') return;
    active.resolve();
    setQueue(prev => prev.slice(1));
  }

  function dismissPrompt(value: string | null) {
    if (!active || active.kind !== 'prompt') return;
    active.resolve(value);
    setQueue(prev => prev.slice(1));
  }

  const tone: AppDialogTone = active?.tone ?? 'default';
  const promptMatches =
    active?.kind === 'prompt' && active.expectedValue != null
      ? promptValue === active.expectedValue
      : true;

  return (
    <>
      {children}
      <AlertDialog
        open={active != null}
        onOpenChange={open => {
          if (open || !active) return;
          if (active.kind === 'confirm') dismissConfirm(false);
          else if (active.kind === 'alert') dismissAlert();
          else dismissPrompt(null);
        }}
      >
        {active && (
          <AlertDialogContent
            className="app-dialog-content border-border bg-card text-card-foreground"
            data-tone={tone}
            data-testid="app-dialog"
            size="default"
          >
            <AlertDialogHeader>
              <AlertDialogTitle
                className="app-dialog-title"
                data-tone={tone}
                data-testid="app-dialog-title"
              >
                {active.title}
              </AlertDialogTitle>
              <AlertDialogDescription
                className="app-dialog-message"
                data-testid="app-dialog-message"
              >
                {active.message}
              </AlertDialogDescription>
            </AlertDialogHeader>

            {active.kind === 'prompt' && (
              <input
                ref={inputRef}
                id={inputId}
                className="app-dialog-input"
                data-testid="app-dialog-input"
                value={promptValue}
                placeholder={active.placeholder}
                autoComplete="off"
                spellCheck={false}
                onChange={e => setPromptValue(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && promptMatches) {
                    e.preventDefault();
                    dismissPrompt(promptValue);
                  }
                }}
              />
            )}

            <AlertDialogFooter>
              {active.kind !== 'alert' && (
                <AlertDialogCancel
                  type="button"
                  data-testid="app-dialog-cancel"
                  onClick={() =>
                    active.kind === 'confirm' ? dismissConfirm(false) : dismissPrompt(null)
                  }
                >
                  {active.cancelLabel}
                </AlertDialogCancel>
              )}
              {active.kind === 'alert' ? (
                <AlertDialogAction
                  type="button"
                  className={actionClass(tone)}
                  data-testid="app-dialog-ok"
                  onClick={dismissAlert}
                >
                  {active.okLabel}
                </AlertDialogAction>
              ) : (
                <AlertDialogAction
                  type="button"
                  className={actionClass(tone)}
                  data-testid="app-dialog-confirm"
                  disabled={active.kind === 'prompt' && !promptMatches}
                  onClick={e => {
                    if (active.kind === 'prompt' && !promptMatches) {
                      e.preventDefault();
                      return;
                    }
                    if (active.kind === 'confirm') dismissConfirm(true);
                    else dismissPrompt(promptValue);
                  }}
                >
                  {active.confirmLabel}
                </AlertDialogAction>
              )}
            </AlertDialogFooter>
          </AlertDialogContent>
        )}
      </AlertDialog>
    </>
  );
}
