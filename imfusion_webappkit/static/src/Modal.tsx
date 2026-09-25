import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function Modal({
  title,
  children,
  footer,
  className,
  hidden = false,
  onClose,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  /** Take the dialog off the screen without unmounting it.
   *
   *  A dialog that asks the user to draw in the viewer has to get out of the
   *  way, and closing it would take the half-filled form with it. */
  hidden?: boolean;
  onClose(): void;
}) {
  const titleId = useId();
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    return () => previouslyFocused?.focus();
  }, []);

  useEffect(() => {
    // While hidden the dialog is not on the screen, so it neither takes the
    // focus nor answers for Escape and Tab.
    if (hidden) return undefined;

    const element = dialog.current;
    const focusable = () =>
      Array.from(element?.querySelectorAll<HTMLElement>(focusableSelector) ?? []);

    (focusable()[0] ?? element)?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== 'Tab') return;

      const items = focusable();
      if (!items.length) {
        event.preventDefault();
        element?.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [hidden]);

  /* Rendered at the document root rather than beside the control that opened it,
     so a dialog is never clipped or stacked by whatever contains that control. */
  return createPortal(
    (
      <div
        className={`modal-backdrop ${hidden ? 'modal-backdrop--hidden' : ''}`}
        role="presentation"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
        <div
          ref={dialog}
          aria-labelledby={titleId}
          aria-modal="true"
          className={`modal ${className ?? ''}`}
          role="dialog"
          tabIndex={-1}
        >
          <h2 id={titleId}>{title}</h2>
          <div className="modal__content">{children}</div>
          {footer && <div className="modal__actions">{footer}</div>}
        </div>
      </div>
    ),
    document.body,
  );
}
