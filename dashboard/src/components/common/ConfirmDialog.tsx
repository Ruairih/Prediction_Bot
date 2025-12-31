/**
 * Confirm Dialog Component
 *
 * A reusable confirmation dialog for dangerous actions.
 * Features:
 * - Standard confirmation with single button click
 * - Enhanced "live mode" confirmation requiring typed confirmation phrase
 * - Accessible with proper ARIA labels and focus management
 * - Theme-aware styling
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import clsx from 'clsx';

export type ConfirmDialogVariant = 'warning' | 'danger' | 'info';

export interface ConfirmDialogProps {
  /** Whether the dialog is open */
  isOpen: boolean;
  /** Called when the dialog should close (cancel or backdrop click) */
  onClose: () => void;
  /** Called when the action is confirmed */
  onConfirm: () => void | Promise<void>;
  /** The title of the dialog */
  title: string;
  /** Description of what will happen */
  description: string;
  /** Additional details or consequences (optional) */
  consequences?: string[];
  /** The text for the confirm button */
  confirmText?: string;
  /** The text for the cancel button */
  cancelText?: string;
  /** Visual variant affecting colors */
  variant?: ConfirmDialogVariant;
  /** If true, requires typing a confirmation phrase */
  requiresTypedConfirmation?: boolean;
  /** The phrase that must be typed for confirmation (defaults to "CONFIRM") */
  confirmationPhrase?: string;
  /** Whether the confirm action is currently loading */
  isLoading?: boolean;
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  consequences,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'warning',
  requiresTypedConfirmation = false,
  confirmationPhrase = 'CONFIRM',
  isLoading = false,
}: ConfirmDialogProps) {
  const [typedValue, setTypedValue] = useState('');
  const [isConfirming, setIsConfirming] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  // Reset typed value when dialog opens/closes
  useEffect(() => {
    if (isOpen) {
      setTypedValue('');
      setIsConfirming(false);
      // Focus the input if typed confirmation is required, otherwise focus confirm button
      setTimeout(() => {
        if (requiresTypedConfirmation && inputRef.current) {
          inputRef.current.focus();
        } else if (confirmButtonRef.current) {
          confirmButtonRef.current.focus();
        }
      }, 50);
    }
  }, [isOpen, requiresTypedConfirmation]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isLoading && !isConfirming) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isLoading, isConfirming, onClose]);

  // Trap focus within dialog
  useEffect(() => {
    if (!isOpen) return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusableElements = dialog.querySelectorAll<HTMLElement>(
      'button, input, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    dialog.addEventListener('keydown', handleTabKey);
    return () => dialog.removeEventListener('keydown', handleTabKey);
  }, [isOpen]);

  const handleConfirm = useCallback(async () => {
    if (requiresTypedConfirmation && typedValue !== confirmationPhrase) {
      return;
    }

    setIsConfirming(true);
    try {
      await onConfirm();
      onClose();
    } catch (error) {
      console.error('Confirm action failed:', error);
    } finally {
      setIsConfirming(false);
    }
  }, [requiresTypedConfirmation, typedValue, confirmationPhrase, onConfirm, onClose]);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !isLoading && !isConfirming) {
      onClose();
    }
  };

  const canConfirm = !requiresTypedConfirmation || typedValue === confirmationPhrase;
  const isDisabled = isLoading || isConfirming || !canConfirm;

  const variantStyles = {
    warning: {
      icon: '!',
      iconBg: 'bg-warning/20',
      iconText: 'text-warning',
      buttonBg: 'bg-warning hover:bg-warning/80',
      buttonText: 'text-black',
    },
    danger: {
      icon: '!',
      iconBg: 'bg-negative/20',
      iconText: 'text-negative',
      buttonBg: 'bg-negative hover:bg-negative/80',
      buttonText: 'text-white',
    },
    info: {
      icon: 'i',
      iconBg: 'bg-info/20',
      iconText: 'text-info',
      buttonBg: 'bg-accent-primary hover:bg-accent-primary/80',
      buttonText: 'text-white',
    },
  };

  const styles = variantStyles[variant];

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="presentation"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleBackdropClick}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className={clsx(
          'relative z-10 w-full max-w-md mx-4',
          'bg-bg-secondary rounded-2xl border border-border shadow-xl',
          'transform transition-all'
        )}
      >
        <div className="p-6">
          {/* Icon */}
          <div className="flex items-center gap-4 mb-4">
            <div
              className={clsx(
                'flex items-center justify-center w-12 h-12 rounded-full',
                styles.iconBg
              )}
              aria-hidden="true"
            >
              <span className={clsx('text-2xl font-bold', styles.iconText)}>
                {styles.icon}
              </span>
            </div>
            <h2
              id="confirm-dialog-title"
              className="text-xl font-semibold text-text-primary"
            >
              {title}
            </h2>
          </div>

          {/* Description */}
          <p
            id="confirm-dialog-description"
            className="text-text-secondary mb-4"
          >
            {description}
          </p>

          {/* Consequences */}
          {consequences && consequences.length > 0 && (
            <div className="mb-4 p-3 rounded-xl bg-bg-tertiary border border-border">
              <div className="text-xs uppercase tracking-wider text-text-muted mb-2">
                This action will:
              </div>
              <ul className="space-y-1">
                {consequences.map((consequence, index) => (
                  <li
                    key={index}
                    className="flex items-start gap-2 text-sm text-text-secondary"
                  >
                    <span className={clsx('mt-0.5', styles.iconText)} aria-hidden="true">
                      -
                    </span>
                    <span>{consequence}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Typed Confirmation */}
          {requiresTypedConfirmation && (
            <div className="mb-4">
              <label
                htmlFor="confirm-input"
                className="block text-sm text-text-secondary mb-2"
              >
                Type{' '}
                <span className="font-mono font-semibold text-text-primary">
                  {confirmationPhrase}
                </span>{' '}
                to confirm:
              </label>
              <input
                ref={inputRef}
                id="confirm-input"
                type="text"
                value={typedValue}
                onChange={(e) => setTypedValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canConfirm) {
                    handleConfirm();
                  }
                }}
                className={clsx(
                  'w-full rounded-lg border px-3 py-2',
                  'bg-bg-tertiary text-text-primary',
                  'focus:outline-none focus:ring-2',
                  typedValue === confirmationPhrase
                    ? 'border-positive focus:ring-positive/50'
                    : 'border-border focus:ring-accent-primary/50'
                )}
                placeholder={confirmationPhrase}
                autoComplete="off"
                spellCheck={false}
                disabled={isLoading || isConfirming}
                aria-describedby="confirm-input-hint"
              />
              <div id="confirm-input-hint" className="sr-only">
                Type the confirmation phrase exactly as shown to enable the confirm button
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading || isConfirming}
              className={clsx(
                'px-4 py-2 rounded-full text-sm font-semibold',
                'border border-border text-text-secondary',
                'hover:text-text-primary hover:bg-bg-tertiary',
                'focus:outline-none focus:ring-2 focus:ring-accent-primary/50',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
              aria-label={cancelText}
            >
              {cancelText}
            </button>
            <button
              ref={confirmButtonRef}
              type="button"
              onClick={handleConfirm}
              disabled={isDisabled}
              className={clsx(
                'px-4 py-2 rounded-full text-sm font-semibold',
                'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-bg-secondary',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors',
                styles.buttonBg,
                styles.buttonText,
                !isDisabled && 'focus:ring-' + (variant === 'danger' ? 'negative' : variant === 'warning' ? 'warning' : 'accent-primary')
              )}
              aria-label={confirmText}
            >
              {isLoading || isConfirming ? (
                <span className="flex items-center gap-2">
                  <svg
                    className="animate-spin h-4 w-4"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Processing...
                </span>
              ) : (
                confirmText
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;
