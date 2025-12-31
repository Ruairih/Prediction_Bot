/**
 * Toast Component
 *
 * A notification toast that supports multiple types and auto-dismiss.
 * Uses theme system colors for consistent styling.
 */
import { useEffect, useCallback } from 'react';
import clsx from 'clsx';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastData {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
}

const typeConfig: Record<ToastType, { icon: string; colorClass: string; bgClass: string; borderClass: string }> = {
  success: {
    icon: '\u2713', // Checkmark
    colorClass: 'text-positive',
    bgClass: 'bg-positive/10',
    borderClass: 'border-positive/30',
  },
  error: {
    icon: '\u2717', // X mark
    colorClass: 'text-negative',
    bgClass: 'bg-negative/10',
    borderClass: 'border-negative/30',
  },
  warning: {
    icon: '\u26A0', // Warning triangle
    colorClass: 'text-warning',
    bgClass: 'bg-warning/10',
    borderClass: 'border-warning/30',
  },
  info: {
    icon: '\u2139', // Info circle
    colorClass: 'text-info',
    bgClass: 'bg-info/10',
    borderClass: 'border-info/30',
  },
};

export function Toast({ toast, onDismiss }: ToastProps) {
  const { id, type, title, message, duration = 5000 } = toast;
  const config = typeConfig[type];

  const handleDismiss = useCallback(() => {
    onDismiss(id);
  }, [id, onDismiss]);

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(handleDismiss, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, handleDismiss]);

  return (
    <div
      role="alert"
      aria-live={type === 'error' ? 'assertive' : 'polite'}
      className={clsx(
        'animate-toast-in pointer-events-auto w-full max-w-sm overflow-hidden',
        'rounded-lg border shadow-lg backdrop-blur-sm',
        'bg-bg-secondary/95',
        config.borderClass
      )}
    >
      <div className="p-4">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <span
            className={clsx(
              'flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold',
              config.bgClass,
              config.colorClass
            )}
          >
            {config.icon}
          </span>

          {/* Content */}
          <div className="flex-1 min-w-0 pt-0.5">
            <p className={clsx('text-sm font-semibold', config.colorClass)}>
              {title}
            </p>
            {message && (
              <p className="mt-1 text-sm text-text-secondary">
                {message}
              </p>
            )}
          </div>

          {/* Dismiss button */}
          <button
            type="button"
            onClick={handleDismiss}
            className={clsx(
              'flex-shrink-0 rounded-md p-1.5',
              'text-text-muted hover:text-text-primary',
              'hover:bg-bg-tertiary focus:outline-none focus:ring-2 focus:ring-accent-primary',
              'transition-colors duration-150'
            )}
            aria-label="Dismiss notification"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Progress bar for auto-dismiss */}
      {duration > 0 && (
        <div className="h-1 w-full bg-bg-tertiary">
          <div
            className={clsx('h-full', config.colorClass.replace('text-', 'bg-'))}
            style={{
              animation: `toast-progress ${duration}ms linear forwards`,
            }}
          />
        </div>
      )}
    </div>
  );
}

interface ToastContainerProps {
  toasts: ToastData[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-3 pointer-events-none"
    >
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
