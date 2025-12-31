/**
 * Toast Context
 *
 * Provides global toast notification management.
 * Supports multiple toast types, stacking, and auto-dismiss.
 */
import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { ToastContainer, ToastData, ToastType } from '../components/common/Toast';

interface ToastOptions {
  title: string;
  message?: string;
  duration?: number;
}

interface ToastContextValue {
  /**
   * Show a toast notification
   */
  showToast: (type: ToastType, options: ToastOptions) => string;

  /**
   * Show a success toast
   */
  success: (title: string, message?: string) => string;

  /**
   * Show an error toast
   */
  error: (title: string, message?: string) => string;

  /**
   * Show a warning toast
   */
  warning: (title: string, message?: string) => string;

  /**
   * Show an info toast
   */
  info: (title: string, message?: string) => string;

  /**
   * Dismiss a specific toast by ID
   */
  dismiss: (id: string) => void;

  /**
   * Dismiss all toasts
   */
  dismissAll: () => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const DEFAULT_DURATION = 5000;
const MAX_TOASTS = 5;

let toastIdCounter = 0;

function generateId(): string {
  return `toast-${Date.now()}-${++toastIdCounter}`;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const dismissAll = useCallback(() => {
    setToasts([]);
  }, []);

  const showToast = useCallback(
    (type: ToastType, options: ToastOptions): string => {
      const id = generateId();
      const newToast: ToastData = {
        id,
        type,
        title: options.title,
        message: options.message,
        duration: options.duration ?? DEFAULT_DURATION,
      };

      setToasts((prev) => {
        // Limit the number of visible toasts
        const updated = [...prev, newToast];
        if (updated.length > MAX_TOASTS) {
          return updated.slice(-MAX_TOASTS);
        }
        return updated;
      });

      return id;
    },
    []
  );

  const success = useCallback(
    (title: string, message?: string) => showToast('success', { title, message }),
    [showToast]
  );

  const error = useCallback(
    (title: string, message?: string) => showToast('error', { title, message }),
    [showToast]
  );

  const warning = useCallback(
    (title: string, message?: string) => showToast('warning', { title, message }),
    [showToast]
  );

  const info = useCallback(
    (title: string, message?: string) => showToast('info', { title, message }),
    [showToast]
  );

  const value: ToastContextValue = {
    showToast,
    success,
    error,
    warning,
    info,
    dismiss,
    dismissAll,
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
